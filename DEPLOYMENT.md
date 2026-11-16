# Deployment Guide: NexusAI Email Intelligence System

Because the application is a unified FastAPI server serving both the REST APIs and the static frontend dashboard, it packages into a single container or service.

---

## 1. Google Cloud Run (Recommended for Production & Serverless)

Google Cloud Run is ideal because:
- **Serverless**: Automatically scales to 0 when idle (no cost when not in use).
- **HTTPS & Custom Domains**: Managed SSL certificates are automatically provisioned.
- **Native Gemini Integration**: Runs in the Google Cloud ecosystem with fast connectivity to Gemini models.

### Step-by-Step Deployment:
1. **Install and authenticate Google Cloud SDK**:
   ```bash
   gcloud auth login
   gcloud config set project YOUR_PROJECT_ID
   ```

2. **Deploy directly from source**:
   ```bash
   gcloud run deploy email-intelligence \
     --source . \
     --region us-central1 \
     --allow-unauthenticated \
     --set-env-vars GEMINI_API_KEY="your_api_key_here",GEMINI_MODEL="gemini-3.8-flash"
   ```

3. GCloud outputs the live public URL:
   ```text
   Service [email-intelligence] revision has been deployed and is serving 100 percent of traffic.
   Service URL: https://email-intelligence-xyz-uc.a.run.app
   ```

---

## 2. Docker / Docker Compose (Local or any Docker Host)

### Build and Run with Docker:
```bash
# Build the container image
docker build -t email-intelligence:latest .

# Run the container
docker run -d -p 8000:8000 \
  -e GEMINI_API_KEY="your_api_key_here" \
  --name email-intelligence \
  email-intelligence:latest
```

### Or using Docker Compose:
```bash
# Pass your API key directly or define it in a .env file
export GEMINI_API_KEY="your_api_key_here"
docker compose up -d
```
Access the application at `http://localhost:8000`.

---

## 3. Render / Railway / Fly.io (One-Click PaaS)

### Deploy to Render:
1. Connect your GitHub repository to [Render.com](https://render.com).
2. Create a **New Web Service**:
   - **Environment**: `Python`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
3. Add Environment Variable:
   - `GEMINI_API_KEY`: `your_key`
4. Click **Deploy**.

### Deploy to Railway:
1. Install Railway CLI or connect via web dashboard:
   ```bash
   railway login
   railway init
   railway up
   ```
2. Set variable:
   ```bash
   railway variables set GEMINI_API_KEY="your_key"
   ```

---

## 4. Linux VM (Ubuntu/Debian on AWS EC2, DigitalOcean, GCP Compute)

### Step 1: Install Python and Clone
```bash
sudo apt update && sudo apt install -y python3-pip python3-venv git
git clone https://github.com/your-username/email-intelligence-system.git /opt/email-intelligence
cd /opt/email-intelligence

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Step 2: Set up Systemd Service
Create `/etc/systemd/system/email-intelligence.service`:
```ini
[Unit]
Description=NexusAI Email Intelligence System
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/opt/email-intelligence
Environment="PATH=/opt/email-intelligence/venv/bin"
Environment="GEMINI_API_KEY=your_key"
ExecStart=/opt/email-intelligence/venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now email-intelligence
```

### Step 3: Reverse Proxy with Caddy (Automatic HTTPS)
Install Caddy:
```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install caddy
```

Edit `/etc/caddy/Caddyfile`:
```caddy
yourdomain.com {
    reverse_proxy 127.0.0.1:8000
}
```

Reload Caddy:
```bash
sudo systemctl reload caddy
```
Caddy will automatically generate and renew Let's Encrypt SSL certificates.

---

## Environment Variables Reference

| Variable | Default | Description |
|---|---|---|
| `PORT` | `8000` | Port the web server listens on. Assigned automatically in Cloud Run / Render / Heroku. |
| `HOST` | `0.0.0.0` (in Docker) | Host IP to bind to. |
| `GEMINI_API_KEY` | *(None)* | Google Gemini API key for `gemini-3.8-flash` structured extraction and tool agent. |
| `GEMINI_MODEL` | `gemini-3.8-flash` | Gemini model variant to invoke. |

