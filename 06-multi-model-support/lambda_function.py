"""
Lambda Function: Multi-Model AI with Memory
Description: Support for multiple Bedrock models (Nova, Claude)
Author: Kay Studios
Date: January 2026
Week: 6
"""

import json
import boto3
import time

# Initialize AWS clients
bedrock_runtime = boto3.client(
    service_name='bedrock-runtime',
    region_name='us-east-2'
)

dynamodb = boto3.resource('dynamodb', region_name='us-east-2')
table = dynamodb.Table('chat-sessions')

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
        'best_for': 'Complex reasoning, longer context'
    },
    'claude-sonnet': {
        'id': 'us.anthropic.claude-3-5-sonnet-20241022-v2:0',
        'name': 'Claude 3.5 Sonnet',
        'family': 'claude',
        'input_cost': 0.003,
        'output_cost': 0.015,
        'speed': 'Medium',
        'best_for': 'Complex reasoning, coding, analysis'
    },
    'claude-haiku': {
        'id': 'us.anthropic.claude-3-haiku-20240307-v1:0',
        'name': 'Claude 3 Haiku',
        'family': 'claude',
        'input_cost': 0.00025,
        'output_cost': 0.00125,
        'speed': 'Fast',
        'best_for': 'Simple tasks, cost-sensitive'
    }
}

def lambda_handler(event, context):
    """Main handler with multi-model support"""
    
    try:
        # Parse request
        if 'body' in event:
            body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
        else:
            body = event
        
        user_prompt = body.get('prompt', '')
        session_id = body.get('sessionId', 'default-session')
        model_key = body.get('model', 'nova-lite')
        
        if not user_prompt:
            return create_response(400, {'error': 'Prompt required'})
        
        if model_key not in MODELS:
            return create_response(400, {
                'error': f'Invalid model. Choose from: {list(MODELS.keys())}'
            })
        
        model_config = MODELS[model_key]
        model_id = model_config['id']
        model_family = model_config['family']
        
        print(f"Session: {session_id}, Model: {model_key}, Prompt: {user_prompt}")
        
        # Get conversation history
        history = get_conversation_history(session_id)
        messages = build_messages_with_context(history, user_prompt)
        
        # Build request body based on model family
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
        
        # Call Bedrock
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
        
        # Estimate tokens and cost
        input_tokens = estimate_tokens(user_prompt + str(history))
        output_tokens = estimate_tokens(full_response)
        estimated_cost = calculate_cost(input_tokens, output_tokens, model_config)
        
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
            }
        })
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return create_response(500, {
            'error': str(e),
            'message': 'Failed to process request'
        })


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
        print(f"Error getting history: {str(e)}")
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
        
        print(f"Saved: {session_id}, model: {model_key}, cost: ${cost:.6f}")
    except Exception as e:
        print(f"Error saving: {str(e)}")


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
