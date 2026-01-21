"""
Lambda Function: Hello Bedrock
Description: Your first serverless AI function using Amazon Bedrock
Author: Kay Studios
Date: January 2026
"""

import json
import boto3
import os

# Initialize Bedrock client
bedrock_runtime = boto3.client(
    service_name='bedrock-runtime',
    region_name='us-east-2'  # Ohio region (closest to you)
)

def lambda_handler(event, context):
    """
    Main Lambda handler function
    
    Args:
        event: API Gateway event object
        context: Lambda context object
        
    Returns:
        API Gateway response object
    """
    
    try:
        # Parse the incoming request
        body = json.loads(event.get('body', '{}'))
        user_prompt = body.get('prompt', 'Hello! Tell me about AWS Bedrock in one sentence.')
        
        print(f"Received prompt: {user_prompt}")
        
        # Prepare the request for Nova
        request_body = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "text": user_prompt
                        }
                    ]
                }
            ],
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
        # Nova returns output differently than Claude
        if 'output' in response_body:
            # Nova format
            ai_response = response_body['output']['message']['content'][0]['text']
        else:
            # Claude format (for future use)
            ai_response = response_body['content'][0]['text']
        
        # Log successful response
        print(f"AI Response: {ai_response[:100]}...")  # First 100 chars
        
        # Return success response
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'  # Enable CORS
            },
            'body': json.dumps({
                'success': True,
                'prompt': user_prompt,
                'response': ai_response,
                'model': 'amazon-nova-lite',
                'timestamp': context.aws_request_id
            })
        }
        
    except Exception as e:
        # Log the error
        print(f"Error: {str(e)}")
        
        # Return error response
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'success': False,
                'error': str(e),
                'message': 'Failed to process request'
            })
        }
