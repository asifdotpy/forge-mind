#!/usr/bin/env bash
# One-command ForgeMind deploy: Cloud Build -> Artifact Registry -> Cloud Run.
#
# Usage:
#   deploy/deploy.sh <PROJECT_ID> [REGION]     # REGION defaults to us-central1
#
# Idempotent: enables APIs, creates the Artifact Registry repository and
# grants image-read IAM only when missing.
set -euo pipefail

PROJECT_ID="${1:?Usage: deploy/deploy.sh <PROJECT_ID> [REGION]}"
REGION="${2:-us-central1}"
SERVICE="forgemind"
AR_REPO="cloud-run-source-deploy"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/${SERVICE}"

# Always operate from the repository root so relative paths resolve.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

echo "=== Deploying ForgeMind to ${PROJECT_ID} (${REGION}) ==="
gcloud config set project "${PROJECT_ID}"

echo "--- Enabling required APIs ---"
gcloud services enable \
  cloudbuild.googleapis.com \
  run.googleapis.com \
  artifactregistry.googleapis.com

echo "--- Ensuring Artifact Registry repository '${AR_REPO}' exists ---"
if ! gcloud artifacts repositories describe "${AR_REPO}" \
      --location="${REGION}" >/dev/null 2>&1; then
  gcloud artifacts repositories create "${AR_REPO}" \
    --repository-format=docker \
    --location="${REGION}" \
    --description="ForgeMind container images"
fi

echo "--- Granting the Cloud Run runtime service account image read access ---"
PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"
RUNTIME_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
gcloud artifacts repositories add-iam-policy-binding "${AR_REPO}" \
  --location="${REGION}" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/artifactregistry.reader" \
  --quiet >/dev/null

echo "--- Submitting Cloud Build pipeline (build -> push -> deploy) ---"
gcloud builds submit \
  --project "${PROJECT_ID}" \
  --config deploy/cloudbuild.yaml \
  --substitutions="_REGION=${REGION},_AR_REPO=${AR_REPO},_SERVICE=${SERVICE}" \
  .

echo "--- Fetching service URL ---"
SERVICE_URL="$(gcloud run services describe "${SERVICE}" \
  --region "${REGION}" \
  --format 'value(status.url)')"

echo "=== Deployment complete ==="
echo "Service URL: ${SERVICE_URL}"
echo "Health check: ${SERVICE_URL}/api/v1/health"
curl -fsS "${SERVICE_URL}/api/v1/health" && echo
