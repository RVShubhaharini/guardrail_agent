#!/bin/bash
# deploy.sh - Automatically builds, tags, pushes Docker container and deploys CloudFormation Stack

set -e

# Configuration
REGION="us-east-1"
STACK_NAME="action-guard-stack"
REPO_NAME="action-guard"

echo "[INFO] Running AWS Deployment automation..."

# 1. Check AWS CLI authentication
if ! aws sts get-caller-identity > /dev/null 2>&1; then
    echo "[ERROR] AWS CLI credentials not found. Please run 'aws configure' first."
    exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_URI="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$REPO_NAME"

echo "[INFO] Authenticated. Account ID: $ACCOUNT_ID"

# 2. Check/Create ECR Repository
echo "[INFO] Verifying ECR repository '$REPO_NAME'..."
aws ecr describe-repositories --repository-names "$REPO_NAME" --region "$REGION" >/dev/null 2>&1 || \
aws ecr create-repository --repository-name "$REPO_NAME" --region "$REGION"

# 3. Docker build
echo "[INFO] Building Docker container image locally..."
docker build -t "$REPO_NAME:latest" .

# 4. Authenticate Docker with ECR
echo "[INFO] Logging into AWS ECR..."
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"

# 5. Tag and Push
echo "[INFO] Tagging and pushing image to ECR..."
docker tag "$REPO_NAME:latest" "$ECR_URI:latest"
docker push "$ECR_URI:latest"

# 6. Deploy CloudFormation stack
echo "[INFO] Starting CloudFormation deployment (ECS Fargate + VPC + DynamoDB)..."
aws cloudformation deploy \
    --template-file infra/cloudformation.yaml \
    --stack-name "$STACK_NAME" \
    --capabilities CAPABILITY_IAM \
    --region "$REGION" \
    --parameter-overrides ImageUri="$ECR_URI:latest" GeminiApiKey="${GEMINI_API_KEY:-}"

# 7. Print output URL
echo "=============================================="
echo "DEPLOYMENT SUCCESSFUL!"
echo "=============================================="
aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query "Stacks[0].Outputs" \
    --region "$REGION" \
    --output table
