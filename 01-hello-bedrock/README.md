# 01 - Hello Bedrock: Your First Serverless AI Function

## What You'll Build

A simple AWS Lambda function that:
- Accepts a prompt via API
- Calls Amazon Bedrock (Claude 3.5 Sonnet)
- Returns an AI-generated response
- Costs ~$0.01 per 100 requests

## Prerequisites

- AWS Account with Bedrock access enabled
- AWS CLI installed and configured
- Basic understanding of Python (we'll learn together!)

## Project Structure

```
01-hello-bedrock/
├── lambda_function.py         # Main Lambda code
├── requirements.txt           # Python dependencies
├── bedrock-lambda-policy.json # IAM permissions
├── deploy.sh                  # Automated deployment
└── README.md                  # This file
```

## Step-by-Step Deployment

### Method 1: Automated (Recommended)

```bash
# Make the deploy script executable
chmod +x deploy.sh

# Run deployment
./deploy.sh
```

That's it! The script handles everything.

### Method 2: Manual (Learn the internals)

#### Step 1: Create IAM Role

```bash
# Create trust policy
cat > trust-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Service": "lambda.amazonaws.com"},
    "Action": "sts:AssumeRole"
  }]
}
EOF

# Create role
aws iam create-role \
    --role-name hello-bedrock-role \
    --assume-role-policy-document file://trust-policy.json
```

#### Step 2: Attach Policies

```bash
# Basic Lambda execution
aws iam attach-role-policy \
    --role-name hello-bedrock-role \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

# Bedrock access
aws iam put-role-policy \
    --role-name hello-bedrock-role \
    --policy-name BedrockAccess \
    --policy-document file://bedrock-lambda-policy.json
```

#### Step 3: Package Function

```bash
zip function.zip lambda_function.py requirements.txt
```

#### Step 4: Create Lambda Function

```bash
# Get role ARN
ROLE_ARN=$(aws iam get-role --role-name hello-bedrock-role --query 'Role.Arn' --output text)

# Create function
aws lambda create-function \
    --function-name hello-bedrock \
    --runtime python3.12 \
    --role $ROLE_ARN \
    --handler lambda_function.lambda_handler \
    --zip-file fileb://function.zip \
    --timeout 30 \
    --memory-size 512 \
    --region us-east-2
```

#### Step 5: Test It

```bash
aws lambda invoke \
    --function-name hello-bedrock \
    --payload '{"body": "{\"prompt\": \"Hello!\"}"}' \
    response.json

cat response.json
```

## Testing

### Test via AWS Console

1. Go to Lambda console
2. Find your `hello-bedrock` function
3. Click "Test"
4. Create test event:
```json
{
  "body": "{\"prompt\": \"Explain AWS Lambda in one sentence.\"}"
}
```
5. Click "Test" and see the response!

### Test via CLI

```bash
aws lambda invoke \
    --function-name hello-bedrock \
    --payload '{"body": "{\"prompt\": \"What is serverless?\"}"}' \
    output.json && cat output.json | python3 -m json.tool
```

## Understanding the Code

### Key Components

```python
# 1. Initialize Bedrock client
bedrock_runtime = boto3.client(
    service_name='bedrock-runtime',
    region_name='us-east-2'
)

# 2. Prepare request for Claude
request_body = {
    "anthropic_version": "bedrock-2023-05-31",
    "max_tokens": 1000,
    "messages": [{"role": "user", "content": prompt}]
}

# 3. Call Bedrock
response = bedrock_runtime.invoke_model(
    modelId='anthropic.claude-3-5-sonnet-20241022-v2:0',
    body=json.dumps(request_body)
)

# 4. Parse response
ai_response = json.loads(response['body'].read())['content'][0]['text']
```

## Common Errors & Solutions

### Error 1: "AccessDeniedException"
**Problem**: Lambda doesn't have permission to call Bedrock
**Solution**: Check IAM policy is attached correctly

### Error 2: "ModelNotFound"
**Problem**: Bedrock model access not enabled
**Solution**: Go to Bedrock console → Model access → Enable models

### Error 3: "Timeout"
**Problem**: Lambda timeout too short
**Solution**: Increase timeout to 30 seconds (already done in deploy script)

### Error 4: "Rate limit exceeded"
**Problem**: Too many requests
**Solution**: Add exponential backoff (Week 3 topic!)

## Cost Breakdown

**Claude 3.5 Sonnet Pricing:**
- Input: $3 per 1M tokens (~750k words)
- Output: $15 per 1M tokens

**Typical Request:**
- Input: 50 tokens (~37 words)
- Output: 200 tokens (~150 words)
- Cost: ~$0.003 per request
- **100 requests = $0.30**

**Lambda Costs:**
- First 1M requests/month: FREE
- After that: $0.20 per 1M requests

**Total for learning: ~$1-5/month**

## What I Learned

(Document your learnings here for your LinkedIn post!)

### Technical Wins
- [ ] Successfully deployed Lambda function
- [ ] Connected Lambda to Bedrock
- [ ] Understood IAM policies
- [ ] Learned boto3 Bedrock SDK

### Challenges
- [ ] IAM permissions confusion
- [ ] JSON parsing issues
- [ ] Understanding Bedrock request format

### Next Steps
- [ ] Add API Gateway (Week 2)
- [ ] Implement error handling
- [ ] Add cost tracking
- [ ] Write LinkedIn post about the experience

## Resources

- [AWS Lambda Docs](https://docs.aws.amazon.com/lambda/)
- [Amazon Bedrock Docs](https://docs.aws.amazon.com/bedrock/)
- [Claude on Bedrock](https://docs.anthropic.com/claude/docs/amazon-bedrock)
- [boto3 Bedrock Reference](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/bedrock-runtime.html)

## LinkedIn Post Template

```
I just deployed my first serverless AI function! 🚀

Built a Lambda function that calls Amazon Bedrock (Claude 3.5 Sonnet) and processes AI requests.

What I learned:
• [Your top learning]
• [Your biggest challenge]
• [Your solution]

Cost for 100 requests: $0.30
Deployment time: 15 minutes
Errors debugged: [Your count]

The best part? Everything is serverless - no servers to manage, only pay for what I use.

Next week: Adding API Gateway so it's actually callable from the web.

#AWS #Serverless #AI #LearningInPublic
```

---

**Created by Kay Studios**
**Part of my 2026 AWS Serverless AI journey**
**Follow along on LinkedIn: [Your profile]**
