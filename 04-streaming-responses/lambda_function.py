"""
Lambda Function: Bedrock Streaming with Memory
Description: Serverless AI with real-time streaming responses
Author: Kay Studios
Week: 4
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

def lambda_handler(event, context):
    """Main Lambda handler with streaming support"""
    
    try:
        # Parse request
        if 'body' in event:
            body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
        else:
            body = event
        
        user_prompt = body.get('prompt', '')
        session_id = body.get('sessionId', 'default-session')
        
        if not user_prompt:
            return {'statusCode': 400, 'body': json.dumps({'error': 'Prompt required'})}
        
        print(f"Session: {session_id}, Prompt: {user_prompt}")
        
        # Get history and build context
        history = get_conversation_history(session_id)
        messages = build_messages_with_context(history, user_prompt)
        
        # Call Bedrock with streaming
        request_body = {
            "messages": messages,
            "inferenceConfig": {"max_new_tokens": 1000}
        }
        
        response = bedrock_runtime.invoke_model_with_response_stream(
            modelId='us.amazon.nova-lite-v1:0',
            body=json.dumps(request_body)
        )
        
        # Process and save stream
        full_response = ""
        chunks = []
        
        for event in response['body']:
            chunk = json.loads(event['chunk']['bytes'].decode())
            if 'contentBlockDelta' in chunk:
                delta = chunk['contentBlockDelta']['delta']
                if 'text' in delta:
                    text_chunk = delta['text']
                    full_response += text_chunk
                    chunks.append(text_chunk)
        
        # Save to DynamoDB
        save_to_dynamodb(session_id, user_prompt, full_response)
        
        # Return complete response for now (we'll add true streaming next)
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'success': True,
                'sessionId': session_id,
                'prompt': user_prompt,
                'response': full_response,
                'model': 'amazon-nova-lite',
                'conversationLength': len(history) + 1
            })
        }
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': str(e), 'message': 'Failed to process'})
        }


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
        if item.get('role') == 'user':
            messages.append({"role": "user", "content": [{"text": item.get('message', '')}]})
        elif item.get('role') == 'assistant':
            messages.append({"role": "assistant", "content": [{"text": item.get('message', '')}]})
    messages.append({"role": "user", "content": [{"text": new_prompt}]})
    return messages


def save_to_dynamodb(session_id, user_message, ai_message):
    """Save conversation"""
    try:
        current_time = int(time.time() * 1000)
        table.put_item(Item={'sessionId': session_id, 'timestamp': current_time, 'role': 'user', 'message': user_message})
        table.put_item(Item={'sessionId': session_id, 'timestamp': current_time + 1, 'role': 'assistant', 'message': ai_message})
        print(f"Saved to DynamoDB: {session_id}")
    except Exception as e:
        print(f"Error saving: {str(e)}")
