"""
Lambda Function: Hello Bedrock with Conversation Memory
Description: Serverless AI function with DynamoDB conversation history
Author: Kay Studios
Date: January 2026
Week: 3
"""

import json
import boto3
import os
import time
from decimal import Decimal

# Initialize AWS clients
bedrock_runtime = boto3.client(
    service_name='bedrock-runtime',
    region_name='us-east-2'
)

dynamodb = boto3.resource('dynamodb', region_name='us-east-2')
table = dynamodb.Table('chat-sessions')

def lambda_handler(event, context):
    """
    Main Lambda handler function with conversation memory
    
    Args:
        event: API Gateway event object
        context: Lambda context object
        
    Returns:
        API Gateway response object
    """
    
    try:
        # Parse the incoming request
        body = json.loads(event.get('body', '{}'))
        user_prompt = body.get('prompt', '')
        session_id = body.get('sessionId', 'default-session')
        
        if not user_prompt:
            return create_response(400, {
                'success': False,
                'error': 'Prompt is required'
            })
        
        print(f"Session: {session_id}, Prompt: {user_prompt}")
        
        # Get conversation history from DynamoDB
        conversation_history = get_conversation_history(session_id)
        
        # Build context-aware prompt
        messages = build_messages_with_context(conversation_history, user_prompt)
        
        # Prepare request for Nova
        request_body = {
            "messages": messages,
            "inferenceConfig": {
                "max_new_tokens": 1000
            }
        }
        
        # Call Bedrock
        response = bedrock_runtime.invoke_model(
            modelId='us.amazon.nova-lite-v1:0',
            body=json.dumps(request_body)
        )
        
        # Parse the response
        response_body = json.loads(response['body'].read())
        
        if 'output' in response_body:
            ai_response = response_body['output']['message']['content'][0]['text']
        else:
            ai_response = response_body['content'][0]['text']
        
        # Save this exchange to DynamoDB
        save_to_dynamodb(session_id, user_prompt, ai_response)
        
        print(f"AI Response: {ai_response[:100]}...")
        
        # Return success response
        return create_response(200, {
            'success': True,
            'sessionId': session_id,
            'prompt': user_prompt,
            'response': ai_response,
            'model': 'amazon-nova-lite',
            'conversationLength': len(conversation_history) + 1
        })
        
    except Exception as e:
        print(f"Error: {str(e)}")
        
        return create_response(500, {
            'success': False,
            'error': str(e),
            'message': 'Failed to process request'
        })


def get_conversation_history(session_id, max_messages=10):
    """
    Retrieve conversation history from DynamoDB
    
    Args:
        session_id: The session identifier
        max_messages: Maximum number of messages to retrieve
        
    Returns:
        List of conversation messages
    """
    try:
        response = table.query(
            KeyConditionExpression='sessionId = :sid',
            ExpressionAttributeValues={
                ':sid': session_id
            },
            ScanIndexForward=False,  # Get most recent first
            Limit=max_messages * 2  # *2 because each exchange has user + AI message
        )
        
        items = response.get('Items', [])
        
        # Sort by timestamp (oldest first for context)
        items.sort(key=lambda x: x['timestamp'])
        
        return items
        
    except Exception as e:
        print(f"Error getting history: {str(e)}")
        return []


def build_messages_with_context(history, new_prompt):
    """
    Build message array with conversation context for Nova
    
    Args:
        history: List of previous messages
        new_prompt: Current user prompt
        
    Returns:
        Messages array formatted for Nova
    """
    messages = []
    
    # Add conversation history
    for item in history:
        if item.get('role') == 'user':
            messages.append({
                "role": "user",
                "content": [{"text": item.get('message', '')}]
            })
        elif item.get('role') == 'assistant':
            messages.append({
                "role": "assistant",
                "content": [{"text": item.get('message', '')}]
            })
    
    # Add new user message
    messages.append({
        "role": "user",
        "content": [{"text": new_prompt}]
    })
    
    return messages


def save_to_dynamodb(session_id, user_message, ai_message):
    """
    Save conversation exchange to DynamoDB
    
    Args:
        session_id: Session identifier
        user_message: User's message
        ai_message: AI's response
    """
    try:
        current_time = int(time.time() * 1000)  # Milliseconds
        
        # Save user message
        table.put_item(
            Item={
                'sessionId': session_id,
                'timestamp': current_time,
                'role': 'user',
                'message': user_message
            }
        )
        
        # Save AI response (slightly later timestamp)
        table.put_item(
            Item={
                'sessionId': session_id,
                'timestamp': current_time + 1,
                'role': 'assistant',
                'message': ai_message
            }
        )
        
        print(f"Saved conversation to DynamoDB for session: {session_id}")
        
    except Exception as e:
        print(f"Error saving to DynamoDB: {str(e)}")
        # Don't fail the request if saving fails


def create_response(status_code, body):
    """
    Create standardized API Gateway response
    
    Args:
        status_code: HTTP status code
        body: Response body dict
        
    Returns:
        API Gateway formatted response
    """
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Allow-Methods': 'OPTIONS,POST,GET'
        },
        'body': json.dumps(body)
    }


# For local testing
if __name__ == "__main__":
    test_event = {
        'body': json.dumps({
            'prompt': 'What is serverless computing?',
            'sessionId': 'test-session-123'
        })
    }
    
    class Context:
        aws_request_id = 'test-request-id'
    
    result = lambda_handler(test_event, Context())
    print(json.dumps(json.loads(result['body']), indent=2))
