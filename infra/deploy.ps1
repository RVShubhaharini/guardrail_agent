# deploy.ps1 - Automated Windows PowerShell script to build, push container and deploy to AWS Fargate

$Region = "us-east-1"
$StackName = "action-guard-stack"
$RepoName = "action-guard"

Write-Host "[INFO] Running AWS Deployment automation (PowerShell)..." -ForegroundColor Cyan

# 1. Verify AWS CLI credentials
$AccountId = aws sts get-caller-identity --query Account --output text
if ($null -eq $AccountId -or $AccountId -match "Error") {
    Write-Error "[ERROR] AWS CLI credentials not found. Run 'aws configure' first."
    exit 1
}

$EcrUri = "$AccountId.dkr.ecr.$Region.amazonaws.com/$RepoName"
Write-Host "[INFO] Authenticated. Account ID: $AccountId" -ForegroundColor Green

# 2. Check/Create ECR Repository
Write-Host "[INFO] Checking ECR Repository..." -ForegroundColor Cyan
aws ecr describe-repositories --repository-names $RepoName --region $Region 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[INFO] ECR Repository not found. Creating..." -ForegroundColor Yellow
    aws ecr create-repository --repository-name $RepoName --region $Region
}

# 3. Docker build locally
Write-Host "[INFO] Compiling local Docker build..." -ForegroundColor Cyan
docker build -t "$RepoName:latest" .

# 4. Authenticate Docker with AWS ECR
Write-Host "[INFO] Logging into AWS ECR registry..." -ForegroundColor Cyan
aws ecr get-login-password --region $Region | docker login --username AWS --password-stdin "$AccountId.dkr.ecr.$Region.amazonaws.com"

# 5. Tag and Push to ECR
Write-Host "[INFO] Tagging and pushing container image to ECR..." -ForegroundColor Cyan
docker tag "$RepoName:latest" "$EcrUri:latest"
docker push "$EcrUri:latest"

# 6. Deploy ECS Fargate Stack
Write-Host "[INFO] Deploying AWS resources via CloudFormation stack..." -ForegroundColor Cyan
$apiKey = if ($env:GEMINI_API_KEY) { $env:GEMINI_API_KEY } else { "" }

aws cloudformation deploy `
    --template-file infra/cloudformation.yaml `
    --stack-name $StackName `
    --capabilities CAPABILITY_IAM `
    --region $Region `
    --parameter-overrides ImageUri="$EcrUri:latest" GeminiApiKey="$apiKey"

# 7. Print endpoint details
Write-Host "==============================================" -ForegroundColor Green
Write-Host "DEPLOYMENT SUCCESSFUL!" -ForegroundColor Green
Write-Host "==============================================" -ForegroundColor Green
aws cloudformation describe-stacks `
    --stack-name $StackName `
    --query "Stacks[0].Outputs" `
    --region $Region `
    --output table
