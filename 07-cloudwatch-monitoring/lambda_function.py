"""
Lambda Function: Multi-Model AI with Enhanced Monitoring
Description: Structured logging, custom metrics, performance tracking
Author: Kay Studios
Date: January 2026
Week: 7
"""

import json
import boto3
import time
import logging
from datetime import datetime

# Configure structured logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
bedrock_runtime = boto3.client(
    service_name='bedrock-runtime',
    region_name='us-east-2'
)

dynamodb = boto3.resource('dynamodb', region_name='us-east-2')
table = dynamodb.Table('chat-sessions')

cloudwatch = boto3.client('cloudwatch', region_name='us-east-2')

# Model configurations
MODELS = {
    'nova-lite': {
        'id': 'us.amazon.nova-lite-v1:0',
        'name': 'Amazon Nova Lite',
        'family': 'nova',
        'input_cost': 0.00006,
        'output_cost': 0.00024,
        'speed': 'Very Fast',
        'best_for': 'Simple queries, high volume'
    },
    'nova-pro': {
        'id': 'us.amazon.nova-pro-v1:0',
        'name': 'Amazon Nova Pro',
        'family': 'nova',
        'input_cost': 0.0008,
        'output_cost': 0.0032,
        'speed': 'Fast',
        'best_for': 'Complex reasoning'
    },
    'claude-sonnet': {
        'id': 'us.anthropic.claude-3-5-sonnet-20241022-v2:0',
        'name': 'Claude 3.5 Sonnet',
        'family': 'claude',
        'input_cost': 0.003,
        'output_cost': 0.015,
        'speed': 'Medium',
        'best_for': 'Complex reasoning, coding'
    }
}


def lambda_handler(event, context):
    """Main handler with enhanced monitoring"""
    
    request_start_time = time.time()
    request_id = context.request_id if hasattr(context, 'request_id') else 'local'
    
    try:
        # Parse request
        if 'body' in event:
            body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
        else:
            body = event
        
        user_prompt = body.get('prompt', '')
        session_id = body.get('sessionId', 'default-session')
        model_key = body.get('model', 'nova-lite')
        
        # Log request start
        log_event('request_started', {
            'requestId': request_id,
            'sessionId': session_id,
            'model': model_key,
            'promptLength': len(user_prompt)
        })
        
        # Validation
        if not user_prompt:
            log_event('validation_error', {
                'requestId': request_id,
                'error': 'Missing prompt'
            })
            return create_response(400, {'error': 'Prompt required'})
        
        if model_key not in MODELS:
            log_event('validation_error', {
                'requestId': request_id,
                'error': 'Invalid model',
                'attempted_model': model_key
            })
            return create_response(400, {
                'error': f'Invalid model. Choose from: {list(MODELS.keys())}'
            })
        
        model_config = MODELS[model_key]
        model_id = model_config['id']
        model_family = model_config['family']
        
        # Get conversation history
        history = get_conversation_history(session_id)
        messages = build_messages_with_context(history, user_prompt)
        
        # Build request
        if model_family == 'claude':
            request_body = {
                "messages": messages,
                "max_tokens": 1000,
                "anthropic_version": "bedrock-2023-05-31"
            }
        else:  # nova
            request_body = {
                "messages": messages,
                "inferenceConfig": {"max_new_tokens": 1000}
            }
        
        # Call Bedrock (track time)
        bedrock_start = time.time()
        
        response = bedrock_runtime.invoke_model_with_response_stream(
            modelId=model_id,
            body=json.dumps(request_body)
        )
        
        # Process stream
        full_response = ""
        for event in response['body']:
            chunk = json.loads(event['chunk']['bytes'].decode())
            if 'contentBlockDelta' in chunk:
                delta = chunk['contentBlockDelta']['delta']
                if 'text' in delta:
                    full_response += delta['text']
        
        bedrock_duration = time.time() - bedrock_start
        
        # Calculate metrics
        input_tokens = estimate_tokens(user_prompt + str(history))
        output_tokens = estimate_tokens(full_response)
        estimated_cost = calculate_cost(input_tokens, output_tokens, model_config)
        
        # Log success
        log_event('request_completed', {
            'requestId': request_id,
            'sessionId': session_id,
            'model': model_key,
            'inputTokens': input_tokens,
            'outputTokens': output_tokens,
            'cost': estimated_cost,
            'bedrockDuration': bedrock_duration,
            'totalDuration': time.time() - request_start_time
        })
        
        # Send custom metrics to CloudWatch
        send_metrics(model_key, estimated_cost, bedrock_duration, input_tokens, output_tokens)
        
        # Save to DynamoDB
        save_to_dynamodb(session_id, user_prompt, full_response, model_key, estimated_cost)
        
        # Return response
        return create_response(200, {
            'success': True,
            'sessionId': session_id,
            'prompt': user_prompt,
            'response': full_response,
            'model': model_config['name'],
            'modelKey': model_key,
            'conversationLength': len(history) + 1,
            'usage': {
                'inputTokens': input_tokens,
                'outputTokens': output_tokens,
                'estimatedCost': round(estimated_cost, 6)
            },
            'performance': {
                'bedrockDuration': round(bedrock_duration, 3),
                'totalDuration': round(time.time() - request_start_time, 3)
            }
        })
        
    except Exception as e:
        # Log error with full context
        log_event('request_failed', {
            'requestId': request_id,
            'error': str(e),
            'errorType': type(e).__name__,
            'duration': time.time() - request_start_time
        })
        
        # Send error metric
        send_error_metric(model_key if 'model_key' in locals() else 'unknown')
        
        return create_response(500, {
            'error': str(e),
            'message': 'Failed to process request'
        })


def log_event(event_type, data):
    """Structured logging helper"""
    log_entry = {
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'event': event_type,
        **data
    }
    logger.info(json.dumps(log_entry))


def send_metrics(model_key, cost, duration, input_tokens, output_tokens):
    """Send custom metrics to CloudWatch"""
    try:
        timestamp = datetime.utcnow()
        
        metrics = [
            # Request count by model
            {
                'MetricName': 'RequestCount',
                'Dimensions': [
                    {'Name': 'Model', 'Value': model_key},
                ],
                'Value': 1,
                'Unit': 'Count',
                'Timestamp': timestamp
            },
            # Cost by model
            {
                'MetricName': 'EstimatedCost',
                'Dimensions': [
                    {'Name': 'Model', 'Value': model_key},
                ],
                'Value': cost,
                'Unit': 'None',
                'Timestamp': timestamp
            },
            # Response time
            {
                'MetricName': 'BedrockDuration',
                'Dimensions': [
                    {'Name': 'Model', 'Value': model_key},
                ],
                'Value': duration,
                'Unit': 'Seconds',
                'Timestamp': timestamp
            },
            # Token usage
            {
                'MetricName': 'InputTokens',
                'Dimensions': [
                    {'Name': 'Model', 'Value': model_key},
                ],
                'Value': input_tokens,
                'Unit': 'Count',
                'Timestamp': timestamp
            },
            {
                'MetricName': 'OutputTokens',
                'Dimensions': [
                    {'Name': 'Model', 'Value': model_key},
                ],
                'Value': output_tokens,
                'Unit': 'Count',
                'Timestamp': timestamp
            }
        ]
        
        cloudwatch.put_metric_data(
            Namespace='AIAssistant',
            MetricData=metrics
        )
    except Exception as e:
        logger.error(f"Failed to send metrics: {str(e)}")


def send_error_metric(model_key):
    """Send error metric"""
    try:
        cloudwatch.put_metric_data(
            Namespace='AIAssistant',
            MetricData=[
                {
                    'MetricName': 'Errors',
                    'Dimensions': [
                        {'Name': 'Model', 'Value': model_key},
                    ],
                    'Value': 1,
                    'Unit': 'Count',
                    'Timestamp': datetime.utcnow()
                }
            ]
        )
    except Exception as e:
        logger.error(f"Failed to send error metric: {str(e)}")


def get_conversation_history(session_id, max_messages=10):
    """Retrieve conversation history"""
    try:
        response = table.query(
            KeyConditionExpression='sessionId = :sid',
            ExpressionAttributeValues={':sid': session_id},
            ScanIndexForward=False,
            Limit=max_messages * 2
        )
        items = response.get('Items', [])
        items.sort(key=lambda x: x['timestamp'])
        return items
    except Exception as e:
        logger.error(f"Error getting history: {str(e)}")
        return []


def build_messages_with_context(history, new_prompt):
    """Build messages with context"""
    messages = []
    for item in history:
        role = item.get('role')
        if role in ['user', 'assistant']:
            messages.append({
                "role": role,
                "content": [{"text": item.get('message', '')}]
            })
    messages.append({
        "role": "user",
        "content": [{"text": new_prompt}]
    })
    return messages


def estimate_tokens(text):
    """Rough token estimation"""
    return len(text) // 4


def calculate_cost(input_tokens, output_tokens, model_config):
    """Calculate estimated cost"""
    input_cost = (input_tokens / 1000) * model_config['input_cost']
    output_cost = (output_tokens / 1000) * model_config['output_cost']
    return input_cost + output_cost


def save_to_dynamodb(session_id, user_message, ai_message, model_key, cost):
    """Save conversation with model info"""
    try:
        ts = int(time.time() * 1000)
        
        table.put_item(Item={
            'sessionId': session_id,
            'timestamp': ts,
            'role': 'user',
            'message': user_message,
            'model': model_key
        })
        
        table.put_item(Item={
            'sessionId': session_id,
            'timestamp': ts + 1,
            'role': 'assistant',
            'message': ai_message,
            'model': model_key,
            'cost': round(cost, 6)
        })
    except Exception as e:
        logger.error(f"Error saving: {str(e)}")


def create_response(status_code, body):
    """Create API Gateway response"""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,x-api-key',
            'Access-Control-Allow-Methods': 'OPTIONS,POST,GET'
        },
        'body': json.dumps(body)
    }
