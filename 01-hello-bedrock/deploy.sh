#!/bin/bash

# Deployment Script for Hello Bedrock Lambda Function
# Author: Kay Studios
# Date: January 2026

set -e  # Exit on any error

# Configuration
FUNCTION_NAME="hello-bedrock"
REGION="us-east-2"
RUNTIME="python3.12"
HANDLER="lambda_function.lambda_handler"
ROLE_NAME="hello-bedrock-role"
POLICY_NAME="BedrockLambdaPolicy"

echo "🚀 Starting deployment of $FUNCTION_NAME..."

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Step 1: Package the function
echo -e "${YELLOW}📦 Step 1: Packaging Lambda function...${NC}"
zip -r function.zip lambda_function.py requirements.txt
echo -e "${GREEN}✓ Package created${NC}"

# Step 2: Create IAM role (if it doesn't exist)
echo -e "${YELLOW}🔐 Step 2: Checking IAM role...${NC}"
if aws iam get-role --role-name $ROLE_NAME 2>/dev/null; then
    echo -e "${GREEN}✓ Role already exists${NC}"
else
    echo "Creating IAM role..."
    
    # Create trust policy
    cat > trust-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

    # Create the role
    aws iam create-role \
        --role-name $ROLE_NAME \
        --assume-role-policy-document file://trust-policy.json \
        --region $REGION
    
    echo "Waiting for role to be ready..."
    sleep 10
    
    echo -e "${GREEN}✓ Role created${NC}"
fi

# Step 3: Attach policies
echo -e "${YELLOW}📋 Step 3: Attaching policies...${NC}"

# Attach basic Lambda execution policy
aws iam attach-role-policy \
    --role-name $ROLE_NAME \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole \
    2>/dev/null || echo "Basic execution policy already attached"

# Create and attach Bedrock policy
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

aws iam put-role-policy \
    --role-name $ROLE_NAME \
    --policy-name $POLICY_NAME \
    --policy-document file://bedrock-lambda-policy.json

echo -e "${GREEN}✓ Policies attached${NC}"

# Wait a bit for IAM to propagate
echo "Waiting for IAM to propagate..."
sleep 10

# Step 4: Create or update Lambda function
echo -e "${YELLOW}⚡ Step 4: Deploying Lambda function...${NC}"

ROLE_ARN=$(aws iam get-role --role-name $ROLE_NAME --query 'Role.Arn' --output text)

if aws lambda get-function --function-name $FUNCTION_NAME --region $REGION 2>/dev/null; then
    echo "Updating existing function..."
    aws lambda update-function-code \
        --function-name $FUNCTION_NAME \
        --zip-file fileb://function.zip \
        --region $REGION
    
    echo -e "${GREEN}✓ Function updated${NC}"
else
    echo "Creating new function..."
    aws lambda create-function \
        --function-name $FUNCTION_NAME \
        --runtime $RUNTIME \
        --role $ROLE_ARN \
        --handler $HANDLER \
        --zip-file fileb://function.zip \
        --timeout 30 \
        --memory-size 512 \
        --region $REGION
    
    echo -e "${GREEN}✓ Function created${NC}"
fi

# Step 5: Test the function
echo -e "${YELLOW}🧪 Step 5: Testing function...${NC}"

TEST_PAYLOAD='{"body": "{\"prompt\": \"Hello! Explain AWS Bedrock in one sentence.\"}"}'

aws lambda invoke \
    --function-name $FUNCTION_NAME \
    --payload "$TEST_PAYLOAD" \
    --region $REGION \
    response.json

echo -e "\n${GREEN}Response:${NC}"
cat response.json | python3 -m json.tool

# Cleanup
rm -f function.zip trust-policy.json response.json

echo -e "\n${GREEN}✅ Deployment complete!${NC}"
echo -e "\n${YELLOW}Next steps:${NC}"
echo "1. Test the function in AWS Console"
echo "2. Add API Gateway (coming in Week 2)"
echo "3. Document what you learned for LinkedIn"
echo -e "\n${YELLOW}Function ARN:${NC}"
aws lambda get-function --function-name $FUNCTION_NAME --region $REGION --query 'Configuration.FunctionArn' --output text
