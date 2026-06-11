Now here's the complete deployment guide tailored to your project:

---
KairoAgent — Google Cloud Run Deployment

Step 0: Install gcloud CLI

# macOS (Homebrew)
brew install google-cloud-sdk

# Then authenticate
gcloud auth login
gcloud config set project kairoagent-497417

---
Step 1: Enable required GCP APIs

Run this once:

gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com

---
Step 2: Store secrets in Secret Manager

Do not bake credentials into the image. Store each secret:

# Elasticsearch
echo -n "https://my-elasticsearch-project-d9aecb.es.europe-west1.gcp.elastic.cloud:443" \
  | gcloud secrets create ES_URL --data-file=-

echo -n "elastic" \
  | gcloud secrets create ES_USERNAME --data-file=-

echo -n "dNZBYMpC*u\$!r7A" \
  | gcloud secrets create ES_PASSWORD --data-file=-

# Gemini
echo -n "AIzaSyDf8uUKnKuGmrlYQeZRXQhxKw2uZxVvCpY" \
  | gcloud secrets create GEMINI_KEY --data-file=-

# MongoDB
echo -n "mongodb+srv://kairoDBAdmin:KvghCaQGqqyK2k7U@kairocluster.wwrd9ag.mongodb.net/" \
  | gcloud secrets create MONGO_URI --data-file=-

# Dune
echo -n "dOJsDRvu4h76ycHpE4YXhoABnWlHTDsQ" \
  | gcloud secrets create DUNE_API_KEY --data-file=-

# CoinMarketCap
echo -n "fabf5af4467e47278a63dbe6b7e212f3" \
  | gcloud secrets create CMC_API_KEY --data-file=-

---
Step 3: Create Artifact Registry repo

gcloud artifacts repositories create kairo \
  --repository-format=docker \
  --location=us-central1

---
Step 4: Build & push the image

Run from your project root (/Users/snehaparihar/KairoAgent):

IMAGE="us-central1-docker.pkg.dev/kairoagent-497417/kairo/kairo-app:latest"

gcloud auth configure-docker us-central1-docker.pkg.dev

docker buildx build -t flask_backend:latest --platform linux/amd64 .
#docker build -t $IMAGE .
docker push $IMAGE

# Grant the service account storage access
gcloud projects add-iam-policy-binding kairoagent-497417 \
  --member="serviceAccount:360527997635-compute@developer.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"

# Also grant the Cloud Build SA (covers both accounts Cloud Build may use)
gcloud projects add-iam-policy-binding kairoagent-497417 \
  --member="serviceAccount:360527997635@cloudbuild.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"

 gcloud projects add-iam-policy-binding kairoagent-497417 \
  --member="serviceAccount:360527997635-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor" 
---
Step 5: Deploy to Cloud Run
gcloud builds submit --config=cloudbuild.yaml --project=kairoagent-497417 .

gcloud run deploy kairo-app \                                              
  --image=us-central1-docker.pkg.dev/kairoagent-497417/kairo/kairo-app:cloudrun \
  --platform=managed \                                                                         
  --region=us-central1 \
  --port=8501 \
  --memory=2Gi --cpu=2 \
  --allow-unauthenticated \
  --set-secrets="ES_URL=ES_URL:latest,ES_USERNAME=ES_USERNAME:latest,ES_PASSWORD=ES_PASSWORD:latest,GEMINI_KEY=GEMINI_KEY:latest,MONGO_URI=MONGO_URI:latest,DUNE_API_KEY=DUNE_API_KEY:latest,CMC_API_KEY=CMC_API_KEY:latest" \
  --set-env-vars="GEMINI_MODEL=gemini-2.5-flash,MONGO_DB=kairo,DEMO_MODE=false,MIN_NARRATIVE_CONFIDENCE=0.7,DUNE_QUERY_WINDOW_HOURS=48"

Cloud Run will return a live HTTPS URL when done.

---
Step 6: Gemini Safety Settings (Hackathon requirement)

Your NarrativeEngine calls Gemini. Add safety settings to app/synthesize/narrative_engine.py where you call generate_content:

from google.generativeai.types import HarmCategory, HarmBlockThreshold

safety_settings = {
    HarmCategory.HARM_CATEGORY_HARASSMENT:        HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH:       HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
}

response = model.generate_content(prompt, safety_settings=safety_settings)

---

# 1. Install crane (Google's container manifest tool — may already be installed)
curl -sL https://github.com/google/go-containerregistry/releases/download/v0.19.1/go-containerregistry_Linux_x86_64.tar.gz \
  | tar -xzf - crane

# 2. Fix the manifest — extract amd64 only, push as new tag
./crane copy \
  --platform linux/amd64 \
  us-central1-docker.pkg.dev/kairoagent-497417/kairo/kairo-app:latest \
  us-central1-docker.pkg.dev/kairoagent-497417/kairo/kairo-app:cloudrun

# 3. Deploy using the fixed single-arch tag
gcloud run deploy kairo-app \
  --image=us-central1-docker.pkg.dev/kairoagent-497417/kairo/kairo-app:cloudrun \
  --platform=managed \
  --region=us-central1 \
  --port=8501 \
  --memory=2Gi \
  --cpu=2 \
  --allow-unauthenticated \
  --set-secrets="ES_URL=ES_URL:latest,ES_USERNAME=ES_USERNAME:latest,ES_PASSWORD=ES_PASSWORD:latest,GEMINI_KEY=GEMINI_KEY:latest,MONGO_URI=MONGO_URI:latest,DUNE_API_KEY=DUNE_API_KEY:latest,CMC_API_KEY=CMC_API_KEY:latest" \
  --set-env-vars="GEMINI_MODEL=gemini-2.5-flash,MONGO_DB=kairo,DEMO_MODE=false,MIN_NARRATIVE_CONFIDENCE=0.7,DUNE_QUERY_WINDOW_HOURS=48"

crane copy --platform linux/amd64 pulls only the amd64 manifest entry out of the OCI image index and pushes it as a plain single-platform manifest — exactly what Cloud Run requires. Note the tag is :cloudrun not :latest on the deploy step.

If crane says the source image has no amd64 variant (meaning the original build was arm64-only), let me know and we'll do a fresh build directly in Cloud Shell with DOCKER_BUILDKIT=0 docker build.