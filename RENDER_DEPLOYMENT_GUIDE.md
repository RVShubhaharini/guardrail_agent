# 🚀 Deploying SentinelAI to Render (Step-by-Step Guide)

Render is one of the easiest, fastest cloud platforms to deploy FastAPI & Docker services for **free** or low-cost.

---

## Option A: Automated Blueprint Deployment (Recommended - 2 Minutes)

If your code is pushed to a GitHub or GitLab repository:

1. **Sign in to Render**: Go to [dashboard.render.com](https://dashboard.render.com/) and log in.
2. **Click "New +"** $\rightarrow$ **Select "Blueprints"**.
3. **Connect Repository**: Select your `sentinelai_guardrail` repository.
4. Render will automatically detect `render.yaml` and configure:
   - **Service Name**: `sentinelai-guardrail`
   - **Environment**: `Docker`
   - **Plan**: `Free`
5. **Set Environment Variables**:
   - Fill in your `GEMINI_API_KEY` (Get it from Google AI Studio).
6. **Click "Apply"**.
   - Render will build the Docker container and deploy your service.
   - Your live URL will be generated: `https://sentinelai-guardrail.onrender.com`

---

## Option B: Manual Web Service Setup (Without render.yaml)

If you prefer setting up via the Render Dashboard manually:

1. **Push your code to GitHub/GitLab**.
2. Open [Render Dashboard](https://dashboard.render.com/) $\rightarrow$ **Click "New +"** $\rightarrow$ **"Web Service"**.
3. **Select "Build and deploy from a Git repository"**.
4. Connect your repo and set the following parameters:
   - **Name**: `sentinelai-guardrail`
   - **Language / Environment**: `Docker` (or `Python 3`)
   - **Region**: Select closest to your users (e.g., Oregon / Singapore / Frankfurt).
   - **Branch**: `main`
   - **Dockerfile Path**: `./Dockerfile` (Leave default if using Docker)
   - *If using Native Python environment*:
     - **Build Command**: `pip install -r requirements.txt`
     - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. **Add Environment Variables**:
   - `GEMINI_API_KEY` = `your_gemini_api_key_here`
   - `ACTIVE_POLICY_VERSION` = `v3`
   - `DRY_RUN` = `false`
   - `USE_DYNAMODB` = `false`
   - `ENABLE_MONITOR` = `false`
6. **Select Plan**: Free Plan ($0/mo) or Starter Plan ($7/mo).
7. **Click "Create Web Service"**.

---

## 🔍 How to Verify Your Live Render Deployment

Once Render displays **"Deployment Live"**:

1. **Check Health Endpoint**:
   ```bash
   curl https://<your-render-app-name>.onrender.com/health
   ```
   *Response:*
   ```json
   {
     "status": "ok",
     "dry_run": false,
     "policy_version": "v3",
     "gmail_mode": "MOCK",
     "monitor_active": false
   }
   ```

2. **Access Interactive Swagger Docs**:
   Open in your browser:
   `https://<your-render-app-name>.onrender.com/docs`

3. **Access Governance Dashboard**:
   Open in your browser:
   `https://<your-render-app-name>.onrender.com/`

---

## ⚠️ Important Render Free Tier Tips

* **Sleep / Spin Down**: Render free services spin down after 15 minutes of inactivity. The first request after a sleep period takes ~30 seconds (cold start).
* **Port Binding**: Render automatically passes `$PORT` (typically port `10000`). SentinelAI's updated [Dockerfile](file:///d:/now_new/Dockerfile) handles `${PORT:-8000}` dynamically.
* **Persistent Audit Logs**: Free tier filesystem is ephemeral (resets on restart). For persistent production audit logs, set `USE_DYNAMODB=true` with AWS credentials or attach a Render Postgres database.
