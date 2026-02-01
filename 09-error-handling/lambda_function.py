"""
Lambda Function: Multi-Model AI with Error Handling & Retry Logic
Description: Graceful error handling, retry with exponential backoff, circuit breaker
Author: Kay Studios
Date: January 2026
Week: 9

Key Concepts:
- Try-catch blocks: Catch errors before they crash the app
- Retry logic: Try again if temporary failures occur
- Exponential backoff: Wait longer between each retry (1s, 2s, 4s, 8s)
- Circuit breaker: Stop trying if service is clearly broken
- Graceful degradation: App works partially even when things fail
"""

import json
import boto3
import time
import logging
from datetime import datetime
from botocore.exceptions import ClientError

# ============================================================================
# LOGGING SETUP
# ============================================================================
# What: Configure how we record what happens
# Why: So we can debug issues when things go wrong
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ============================================================================
# AWS CLIENT INITIALIZATION
# ============================================================================
# What: Create connections to AWS services
# Why: We need these to call Bedrock, DynamoDB, and CloudWatch
bedrock_runtime = boto3.client(
    service_name='bedrock-runtime',
    region_name='us-east-2'
)

dynamodb = boto3.resource('dynamodb', region_name='us-east-2')
table = dynamodb.Table('chat-sessions')

cloudwatch = boto3.client('cloudwatch', region_name='us-east-2')

# ============================================================================
# CONFIGURATION
# ============================================================================

# Model configurations (same as Week 6)
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
    }
}

# User-friendly error messages
# What: Messages users see when things fail
# Why: Better than "Error 500" - users understand what went wrong
FALLBACK_RESPONSES = {
    'bedrock_unavailable': "I'm having trouble connecting to my AI brain right now. Please try again in a moment! 🤖",
    'bedrock_timeout': "That request is taking longer than expected. Try asking something simpler?",
    'database_error': "I can answer your question, but I might not remember this conversation.",
    'rate_limit': "Whoa, you're asking questions too quickly! Give me a moment to catch my breath. 😅",
    'validation_error': "Hmm, I didn't quite understand that request. Could you try rephrasing?",
    'unknown_error': "Something unexpected happened. Our team has been notified!"
}

# Retry configuration
# What: Settings for how many times we retry and how long we wait
# Why: Don't give up immediately, but don't retry forever either
MAX_RETRIES = 3  # Try up to 3 times
INITIAL_BACKOFF = 1  # Start with 1 second wait
MAX_BACKOFF = 16  # Don't wait more than 16 seconds

# Circuit breaker state
# What: Track if a service is down so we don't keep trying
# Why: Save money and fail fast instead of wasting time
circuit_breaker = {
    'bedrock': {'failures': 0, 'last_failure': None, 'is_open': False},
    'dynamodb': {'failures': 0, 'last_failure': None, 'is_open': False}
}

# ============================================================================
# CIRCUIT BREAKER FUNCTIONS
# ============================================================================

def check_circuit_breaker(service_name):
    """
    Check if we should attempt to call a service
    
    What: Decides if circuit breaker is open (service is broken)
    Why: Don't waste time/money calling a service that's clearly down
    
    Args:
        service_name: 'bedrock' or 'dynamodb'
    
    Returns:
        True if we should try, False if circuit is open
    
    How it works:
        - If 5+ failures in a row → circuit opens (stop trying)
        - After 60 seconds → circuit closes (try again)
    """
    breaker = circuit_breaker[service_name]
    
    # Circuit is closed - we can try
    if not breaker['is_open']:
        return True
    
    # Circuit is open - check if enough time has passed
    if breaker['last_failure']:
        time_since_failure = time.time() - breaker['last_failure']
        if time_since_failure > 60:  # 60 seconds passed
            # Reset and try again
            log_event('circuit_breaker_reset', {
                'service': service_name,
                'reason': 'timeout_elapsed'
            })
            breaker['is_open'] = False
            breaker['failures'] = 0
            return True
    
    # Circuit still open
    log_event('circuit_breaker_blocked', {'service': service_name})
    return False


def record_success(service_name):
    """
    Record successful call - reset circuit breaker
    
    What: Clear the failure count after success
    Why: Service is working again, reset the circuit breaker
    """
    breaker = circuit_breaker[service_name]
    breaker['failures'] = 0
    breaker['is_open'] = False


def record_failure(service_name):
    """
    Record failed call - might open circuit breaker
    
    What: Track failures and open circuit if too many
    Why: After 5 failures, assume service is down and stop trying
    """
    breaker = circuit_breaker[service_name]
    breaker['failures'] += 1
    breaker['last_failure'] = time.time()
    
    if breaker['failures'] >= 5:
        breaker['is_open'] = True
        log_event('circuit_breaker_opened', {
            'service': service_name,
            'failure_count': breaker['failures']
        })

# ============================================================================
# RETRY LOGIC WITH EXPONENTIAL BACKOFF
# ============================================================================

def call_bedrock_with_retry(model_id, request_body, model_family):
    """
    Call Bedrock AI with automatic retry on failures
    
    What: Try to call Bedrock, retry if it fails temporarily
    Why: Network hiccups happen - retry before giving up
    
    How exponential backoff works:
        Attempt 1: Fails → wait 1 second
        Attempt 2: Fails → wait 2 seconds  
        Attempt 3: Fails → wait 4 seconds
        Attempt 4: Give up
    
    This gives the service time to recover without hammering it.
    """
    
    # Check circuit breaker first
    if not check_circuit_breaker('bedrock'):
        raise Exception(FALLBACK_RESPONSES['bedrock_unavailable'])
    
    last_error = None
    
    # Try up to MAX_RETRIES times
    for attempt in range(MAX_RETRIES):
        try:
            log_event('bedrock_attempt', {
                'attempt': attempt + 1,
                'max_retries': MAX_RETRIES,
                'model': model_id
            })
            
            # Actually call Bedrock
            response = bedrock_runtime.invoke_model_with_response_stream(
                modelId=model_id,
                body=json.dumps(request_body)
            )
            
            # Success! Reset circuit breaker
            record_success('bedrock')
            
            # Process the streaming response
            full_response = ""
            for event in response['body']:
                chunk = json.loads(event['chunk']['bytes'].decode())
                if 'contentBlockDelta' in chunk:
                    delta = chunk['contentBlockDelta']['delta']
                    if 'text' in delta:
                        full_response += delta['text']
            
            return full_response
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            last_error = e
            
            log_event('bedrock_error', {
                'attempt': attempt + 1,
                'error_code': error_code,
                'error_message': str(e)
            })
            
            # Determine if we should retry
            if error_code in ['ThrottlingException', 'ServiceUnavailableException', 
                            'TooManyRequestsException']:
                # Retryable errors - temporary problems
                if attempt < MAX_RETRIES - 1:  # Not the last attempt
                    # Calculate wait time: 1s, 2s, 4s, 8s, 16s (exponential)
                    wait_time = min(INITIAL_BACKOFF * (2 ** attempt), MAX_BACKOFF)
                    
                    log_event('bedrock_retry', {
                        'attempt': attempt + 1,
                        'wait_seconds': wait_time,
                        'reason': error_code
                    })
                    
                    time.sleep(wait_time)  # Wait before retry
                    continue  # Try again
                    
            elif error_code in ['ValidationException', 'AccessDeniedException']:
                # Non-retryable errors - permanent problems, don't waste time
                record_failure('bedrock')
                raise Exception(FALLBACK_RESPONSES['validation_error'])
                
            else:
                # Unknown error - log and retry
                if attempt < MAX_RETRIES - 1:
                    time.sleep(INITIAL_BACKOFF * (2 ** attempt))
                    continue
        
        except Exception as e:
            # Unexpected error
            last_error = e
            log_event('bedrock_unexpected_error', {
                'attempt': attempt + 1,
                'error': str(e)
            })
            
            if attempt < MAX_RETRIES - 1:
                time.sleep(INITIAL_BACKOFF * (2 ** attempt))
                continue
    
    # All retries failed
    record_failure('bedrock')
    raise Exception(FALLBACK_RESPONSES['bedrock_unavailable'])


def save_to_dynamodb_with_retry(session_id, user_message, ai_message, model_key, cost):
    """
    Save conversation to DynamoDB with retry logic
    
    What: Save to database, retry if it fails
    Why: Database can be slow/unavailable temporarily
    
    Note: We try to save, but if it fails completely, we still return
    the AI response to the user (graceful degradation)
    """
    
    if not check_circuit_breaker('dynamodb'):
        log_event('dynamodb_skipped', {'reason': 'circuit_breaker_open'})
        return False  # Skip saving, but don't crash
    
    for attempt in range(MAX_RETRIES):
        try:
            ts = int(time.time() * 1000)
            
            # Save user message
            table.put_item(Item={
                'sessionId': session_id,
                'timestamp': ts,
                'role': 'user',
                'message': user_message,
                'model': model_key
            })
            
            # Save AI response
            table.put_item(Item={
                'sessionId': session_id,
                'timestamp': ts + 1,
                'role': 'assistant',
                'message': ai_message,
                'model': model_key,
                'cost': round(cost, 6)
            })
            
            record_success('dynamodb')
            return True
            
        except Exception as e:
            log_event('dynamodb_error', {
                'attempt': attempt + 1,
                'error': str(e)
            })
            
            if attempt < MAX_RETRIES - 1:
                time.sleep(INITIAL_BACKOFF * (2 ** attempt))
                continue
    
    # All retries failed - but we don't crash, just log it
    record_failure('dynamodb')
    log_event('dynamodb_save_failed', {
        'sessionId': session_id,
        'warning': 'Conversation not saved'
    })
    return False

# ============================================================================
# MAIN LAMBDA HANDLER
# ============================================================================

def lambda_handler(event, context):
    """
    Main entry point - now with comprehensive error handling!
    
    What: Process user request with graceful error handling
    Why: App should never crash - always return something useful
    """
    
    request_start_time = time.time()
    request_id = context.request_id if hasattr(context, 'request_id') else 'local'
    
    try:
        # ===== PARSE REQUEST =====
        # What: Extract the user's request from the event
        # Why: We need to know what the user asked
        if 'body' in event:
            body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
        else:
            body = event
        
        user_prompt = body.get('prompt', '')
        session_id = body.get('sessionId', 'default-session')
        model_key = body.get('model', 'nova-lite')
        
        log_event('request_started', {
            'requestId': request_id,
            'sessionId': session_id,
            'model': model_key,
            'promptLength': len(user_prompt)
        })
        
        # ===== VALIDATION =====
        # What: Check if the request is valid
        # Why: Catch bad requests early (non-retryable errors)
        if not user_prompt:
            return create_response(400, {
                'success': False,
                'error': 'Prompt is required'
            })
        
        if len(user_prompt) > 10000:
            return create_response(400, {
                'success': False,
                'error': 'Prompt too long (max 10,000 characters)'
            })
        
        if model_key not in MODELS:
            return create_response(400, {
                'success': False,
                'error': f'Invalid model. Choose from: {list(MODELS.keys())}'
            })
        
        model_config = MODELS[model_key]
        model_id = model_config['id']
        model_family = model_config['family']
        
        # ===== GET CONVERSATION HISTORY =====
        # What: Load past conversation (with error handling)
        # Why: Provide context to the AI
        try:
            history = get_conversation_history(session_id)
        except Exception as e:
            # If getting history fails, continue with empty history
            log_event('history_error', {'error': str(e)})
            history = []
        
        messages = build_messages_with_context(history, user_prompt)
        
        # ===== BUILD REQUEST =====
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
        
        # ===== CALL BEDROCK (WITH RETRY) =====
        # What: Get AI response with automatic retry
        # Why: This is the most important part - if this fails, retry!
        bedrock_start = time.time()
        
        try:
            full_response = call_bedrock_with_retry(model_id, request_body, model_family)
        except Exception as e:
            # Bedrock failed completely - return fallback
            log_event('bedrock_failed_completely', {
                'requestId': request_id,
                'error': str(e)
            })
            
            return create_response(503, {
                'success': False,
                'error': str(e),
                'canRetry': True
            })
        
        bedrock_duration = time.time() - bedrock_start
        
        # ===== CALCULATE METRICS =====
        input_tokens = estimate_tokens(user_prompt + str(history))
        output_tokens = estimate_tokens(full_response)
        estimated_cost = calculate_cost(input_tokens, output_tokens, model_config)
        
        # ===== SAVE TO DATABASE (WITH RETRY) =====
        # What: Save conversation (but don't crash if it fails)
        # Why: Graceful degradation - answer is more important than saving
        save_success = save_to_dynamodb_with_retry(
            session_id, user_prompt, full_response, model_key, estimated_cost
        )
        
        # ===== SEND METRICS (BEST EFFORT) =====
        # What: Send CloudWatch metrics (but don't crash if it fails)
        # Why: Metrics are nice to have, but not critical
        try:
            send_metrics(model_key, estimated_cost, bedrock_duration, input_tokens, output_tokens)
        except Exception as e:
            log_event('metrics_error', {'error': str(e)})
            # Continue anyway
        
        # ===== LOG SUCCESS =====
        log_event('request_completed', {
            'requestId': request_id,
            'sessionId': session_id,
            'model': model_key,
            'cost': estimated_cost,
            'duration': time.time() - request_start_time,
            'savedToDb': save_success
        })
        
        # ===== RETURN RESPONSE =====
        response_data = {
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
        }
        
        # Add warning if conversation wasn't saved
        if not save_success:
            response_data['warning'] = FALLBACK_RESPONSES['database_error']
        
        return create_response(200, response_data)
        
    except Exception as e:
        # ===== CATCH-ALL ERROR HANDLER =====
        # What: Catch any unexpected errors
        # Why: Never let the Lambda crash
        log_event('request_failed', {
            'requestId': request_id,
            'error': str(e),
            'errorType': type(e).__name__,
            'duration': time.time() - request_start_time
        })
        
        send_error_metric(model_key if 'model_key' in locals() else 'unknown')
        
        return create_response(500, {
            'success': False,
            'error': FALLBACK_RESPONSES['unknown_error'],
            'canRetry': True
        })

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def log_event(event_type, data):
    """Structured logging helper"""
    log_entry = {
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'event': event_type,
        **data
    }
    logger.info(json.dumps(log_entry))


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


def send_metrics(model_key, cost, duration, input_tokens, output_tokens):
    """Send custom metrics to CloudWatch"""
    try:
        timestamp = datetime.utcnow()
        
        metrics = [
            {
                'MetricName': 'RequestCount',
                'Dimensions': [{'Name': 'Model', 'Value': model_key}],
                'Value': 1,
                'Unit': 'Count',
                'Timestamp': timestamp
            },
            {
                'MetricName': 'EstimatedCost',
                'Dimensions': [{'Name': 'Model', 'Value': model_key}],
                'Value': cost,
                'Unit': 'None',
                'Timestamp': timestamp
            },
            {
                'MetricName': 'BedrockDuration',
                'Dimensions': [{'Name': 'Model', 'Value': model_key}],
                'Value': duration,
                'Unit': 'Seconds',
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
                    'Dimensions': [{'Name': 'Model', 'Value': model_key}],
                    'Value': 1,
                    'Unit': 'Count',
                    'Timestamp': datetime.utcnow()
                }
            ]
        )
    except Exception as e:
        logger.error(f"Failed to send error metric: {str(e)}")


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
