# ☁️ SentinelAI AWS Fast-Track Deployment Guide

Deploying **SentinelAI** on Amazon Web Services (AWS) is fast, easy, and production-ready. Below are the 3 fastest deployment options tailored for continuous background monitoring and persistent threat vaults.

---

## 🚀 Option 1: 5-Minute Fast-Track AWS EC2 Deployment (Recommended)

EC2 is ideal because it allows continuous 24/7 background monitoring threads and persistent local disk vault storage (`data/quarantine_vault.json`).

### Step 1: Launch an EC2 Instance on AWS Console
1. Log in to the [AWS Management Console](https://aws.amazon.com/console/) and navigate to **EC2**.
2. Click **Launch Instance**:
   * **Name:** `SentinelAI-Server`
   * **OS Image:** `Ubuntu 22.04 LTS` (or Amazon Linux 2023)
   * **Instance Type:** `t3.small` (or `t2.micro` Free Tier)
   * **Key Pair:** Select or create an SSH key pair (`.pem`).

### Step 2: Configure Security Group (Firewall)
In the **Network Settings** section during launch (or under **Security Groups** after launch), add the following **Inbound Rules**:

| Type | Protocol | Port Range | Source | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| **Custom TCP** | TCP | `8000` | `0.0.0.0/0` | SentinelAI FastAPI Dashboard |
| **HTTP** | TCP | `80` | `0.0.0.0/0` | Web Access |
| **SSH** | TCP | `22` | `My IP` | Secure Shell Access |

Click **Launch Instance**.

---

### Step 3: Connect to EC2 & Run Automated Deployment Script
Open your PowerShell or Terminal and SSH into your EC2 instance:
```bash
ssh -i "your-key.pem" ubuntu@<YOUR_EC2_PUBLIC_IP>
```

Once connected inside your EC2 instance, execute these **3 commands**:
```bash
# 1. Clone your repository
git clone <YOUR_GIT_REPOSITORY_URL>
cd guardrail_agent

# 2. Grant execution permissions to the setup script
chmod +x scripts/deploy_aws_ec2.sh

# 3. Run the automated installer script
./scripts/deploy_aws_ec2.sh
```

---

### Step 4: Update `.env` with Your API Keys
Edit the `.env` file on your EC2 instance to add your API keys:
```bash
nano .env
```
Update these lines:
```env
PORT=8000
POLICY_VERSION=v3
DRY_RUN_MODE=false
ENABLE_MONITOR=true
GROQ_API_KEY=your_actual_groq_api_key
GEMINI_API_KEY=your_actual_gemini_api_key
```
Press `Ctrl + O` then `Enter` to save, and `Ctrl + X` to exit.

Restart the container to apply your keys:
```bash
sudo docker-compose restart
```

---

### Step 5: Open Your SentinelAI Live Dashboard
Open your web browser and go to:
```text
http://<YOUR_EC2_PUBLIC_IP>:8000
```
Your SentinelAI Live Governance Dashboard is now **100% active and running live on AWS**!

---

## ⚡ Option 2: AWS App Runner (Serverless Container Deployment)

AWS App Runner is a fully managed container service that provides automatic HTTPS endpoints.

### Steps:
1. Push your code or container image to **AWS ECR** (Elastic Container Registry):
   ```bash
   aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <AWS_ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com
   docker build -t sentinel-ai .
   docker tag sentinel-ai:latest <AWS_ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/sentinel-ai:latest
   docker push <AWS_ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/sentinel-ai:latest
   ```
2. Navigate to **AWS App Runner** in the AWS Console.
3. Click **Create an App Runner Service**:
   * **Source:** Container Registry (ECR)
   * **Port:** `8000`
   * **Environment Variables:** Add `GROQ_API_KEY`, `GEMINI_API_KEY`, `POLICY_VERSION=v3`, `ENABLE_MONITOR=true`.
4. Click **Create & Deploy**. AWS will issue an SSL/HTTPS URL (e.g., `https://xxxxxx.us-east-1.awsapprunner.com`).

---

## 💡 Option 3: AWS Lightsail ($3.50/month Low-Cost Instance)

AWS Lightsail offers simple fixed monthly pricing ($3.50/mo).

### Steps:
1. Navigate to **AWS Lightsail** in the Console.
2. Click **Create Instance** $\to$ Select **OS Only (Ubuntu 22.04)**.
3. Choose the $3.50/month plan and click **Create Instance**.
4. Under the **Networking** tab for your instance, click **Add Firewall Rule**:
   * **Custom TCP**, Port `8000`.
5. Connect via SSH browser terminal and run:
   ```bash
   git clone <YOUR_GIT_REPOSITORY_URL>
   cd guardrail_agent
   chmod +x scripts/deploy_aws_ec2.sh && ./scripts/deploy_aws_ec2.sh
   ```

---

## 🔍 Managing & Monitoring Your AWS Deployment

Useful SSH commands on EC2 / Lightsail:

```bash
# View live container logs
sudo docker-compose logs -f

# Check container status
sudo docker-compose ps

# Restart SentinelAI server
sudo docker-compose restart

# Stop server
sudo docker-compose down
```

---
*AWS Deployment Guide for SentinelAI ActionGuard Systems.*
