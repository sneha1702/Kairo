# 🚀 Deployment Guide

This guide covers how to deploy the Narrative Evolution Agent to production.

## Deployment Options

### 1. Local Development

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure secrets
cp .env.example .env
# Edit .env with your credentials

# Run the app
streamlit run app.py
```

### 2. Docker Deployment

#### Option A: Build and Run Locally

```bash
# Build image
docker build -t narrative-agent:latest .

# Run container
docker run -p 8501:8501 \
  -e ES_URL="your-es-url" \
  -e ES_USERNAME="elastic" \
  -e ES_PASSWORD="your-password" \
  -e GEMINI_KEY="your-gemini-key" \
  narrative-agent:latest
```

#### Option B: Docker Compose

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  narrative-agent:
    build: .
    ports:
      - "8501:8501"
    environment:
      ES_URL: ${ES_URL}
      ES_USERNAME: ${ES_USERNAME}
      ES_PASSWORD: ${ES_PASSWORD}
      GEMINI_KEY: ${GEMINI_KEY}
    volumes:
      - ./data:/app/data
    restart: unless-stopped
```

Run with:

```bash
docker-compose up -d
```

### 3. Streamlit Cloud (Easiest)

1. Push repository to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Click "New app"
4. Select your GitHub repo and branch
5. Add secrets in Settings:
   - `ES_URL`
   - `ES_USERNAME`
   - `ES_PASSWORD`
   - `GEMINI_KEY`
6. Deploy!

### 4. AWS Deployment

#### Using ECS (Recommended)

1. Create Dockerfile (see below)
2. Push image to ECR:

```bash
# Authenticate with ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 123456789.dkr.ecr.us-east-1.amazonaws.com

# Build and push
docker build -t narrative-agent:latest .
docker tag narrative-agent:latest 123456789.dkr.ecr.us-east-1.amazonaws.com/narrative-agent:latest
docker push 123456789.dkr.ecr.us-east-1.amazonaws.com/narrative-agent:latest
```

3. Create ECS task definition:

```json
{
  "family": "narrative-agent",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "256",
  "memory": "512",
  "containerDefinitions": [
    {
      "name": "narrative-agent",
      "image": "123456789.dkr.ecr.us-east-1.amazonaws.com/narrative-agent:latest",
      "portMappings": [
        {
          "containerPort": 8501,
          "hostPort": 8501,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {
          "name": "ES_URL",
          "value": "your-es-url"
        }
      ],
      "secrets": [
        {
          "name": "ES_PASSWORD",
          "valueFrom": "arn:aws:secretsmanager:..."
        }
      ]
    }
  ]
}
```

4. Create ECS service and attach ALB

### 5. GCP Cloud Run

```bash
# Create app.yaml
cat > app.yaml << EOF
runtime: python39
entrypoint: streamlit run app.py
env_variables:
  ES_URL: "your-es-url"
EOF

# Create .gcloudignore
cat > .gcloudignore << EOF
.git
.gitignore
.venv
__pycache__
EOF

# Deploy
gcloud run deploy narrative-agent \
  --source . \
  --platform managed \
  --set-env-vars ES_URL=your-url,ES_USERNAME=elastic,GEMINI_KEY=xxx
```

### 6. Kubernetes Deployment

Create `k8s/deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: narrative-agent
spec:
  replicas: 2
  selector:
    matchLabels:
      app: narrative-agent
  template:
    metadata:
      labels:
        app: narrative-agent
    spec:
      containers:
      - name: narrative-agent
        image: narrative-agent:latest
        ports:
        - containerPort: 8501
        env:
        - name: ES_URL
          valueFrom:
            configMapKeyRef:
              name: narrative-config
              key: es-url
        - name: ES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: narrative-secrets
              key: es-password
        - name: GEMINI_KEY
          valueFrom:
            secretKeyRef:
              name: narrative-secrets
              key: gemini-key
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /_stcore/health
            port: 8501
          initialDelaySeconds: 10
          periodSeconds: 10
```

Deploy with:

```bash
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
```

## Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8501

# Health check
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# Run
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

## Environment Variables

Required for all deployments:

```bash
# Elasticsearch
ES_URL="https://your-cluster.es.region.cloud:443"
ES_USERNAME="elastic"
ES_PASSWORD="your-password"

# Google Gemini
GEMINI_KEY="your-gemini-api-key"

# Optional
LOG_LEVEL="INFO"
DEBUG="false"
MIN_NARRATIVE_CONFIDENCE="0.5"
```

## Security Checklist

- [ ] Use VPC/firewall for Elasticsearch
- [ ] Enable authentication on Streamlit
- [ ] Use HTTPS/TLS for all connections
- [ ] Store secrets in secret manager (not .env in production)
- [ ] Rotate API keys regularly
- [ ] Monitor and log all access
- [ ] Set up rate limiting on Gemini API
- [ ] Enable IP whitelisting where possible
- [ ] Backup Elasticsearch indices daily

## Monitoring

### Logs

Monitor these metrics:

```bash
# Check Elasticsearch connectivity
curl -u elastic:password https://your-es-url/_cluster/health

# Monitor API usage
grep "GEMINI" logs/*.log | tail -20

# Check disk space
df -h /data
```

### Alerting

Set up alerts for:

- Elasticsearch connection failures
- High Gemini API error rate
- Narrative detection failures
- Memory/CPU usage spikes

### Metrics to Track

- Narratives detected per day
- Average confidence scores
- API latency (ES queries)
- Gemini API costs
- User engagement

## Scaling Considerations

1. **Elasticsearch**: Increase shards/replicas for higher throughput
2. **Caching**: Cache narrative history to reduce ES queries
3. **Batch Processing**: Process multiple detection requests in parallel
4. **Load Balancing**: Use ALB/NLB for multiple instances
5. **Database**: Consider adding PostgreSQL for user data

## Troubleshooting

### Connection Issues

```bash
# Test Elasticsearch
curl -u elastic:password https://your-es-url

# Test Gemini API
python -c "import google.generativeai as genai; print(genai.__version__)"
```

### Performance Issues

1. Check Elasticsearch query times
2. Monitor Gemini API latency
3. Enable caching for frequently accessed narratives
4. Increase container memory/CPU

### High Costs

1. Reduce Gemini model calls (cache results)
2. Implement rate limiting
3. Optimize Elasticsearch queries
4. Use batch processing

## Maintenance

### Regular Tasks

- [ ] Monitor API usage and costs
- [ ] Review and update narrative detection prompts
- [ ] Clean up old narrative history (>30 days)
- [ ] Backup Elasticsearch data
- [ ] Update dependencies monthly
- [ ] Review security logs

### Updates

```bash
# Update dependencies
pip install --upgrade -r requirements.txt

# Rebuild Docker image
docker build -t narrative-agent:latest .

# Deploy new version
docker push narrative-agent:latest
```

## Support

For deployment issues:
1. Check logs first
2. Review environment variables
3. Verify API credentials
4. Test connectivity to services
5. Check resource limits
