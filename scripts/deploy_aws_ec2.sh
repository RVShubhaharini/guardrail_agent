#!/bin/bash
set -e

echo "=========================================================="
echo "🛡️ SentinelAI AWS EC2 Fast-Track Automated Deployment Script"
echo "=========================================================="

# 1. Update system packages & install Docker
echo "Step 1: Installing Docker & Docker Compose..."
sudo apt-get update -y
sudo apt-get install -y docker.io docker-compose git curl

# 2. Start and enable Docker daemon
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -aG docker $USER

# 3. Create .env if missing
if [ ! -f .env ]; then
    echo "Creating default .env configuration file..."
    cat <<EOT > .env
PORT=8000
POLICY_VERSION=v3
DRY_RUN_MODE=false
ENABLE_MONITOR=true
MONITOR_INTERVAL=15
GROQ_API_KEY=your_groq_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
EOT
    echo "⚠️ Please update .env with your real API keys!"
fi

# 4. Create data directory for persistence
mkdir -p data

# 5. Build and launch Docker container
echo "Step 2: Building and launching SentinelAI Container..."
sudo docker-compose down || true
sudo docker-compose up -d --build

echo "=========================================================="
echo "✅ SentinelAI successfully deployed to AWS EC2!"
echo "Public Dashboard: http://$(curl -s ifconfig.me):8000"
echo "=========================================================="
