# ForgeMind v3.0 — Spin-Up & Reproduction Guide

This guide proves the project is reproducible locally and deployable to Google
Cloud, satisfying the hackathon "reproducible setup" requirement.

## Prerequisites
- Python ≥ 3.11, `uv` (https://docs.astral.sh/uv/)
- (Optional, for the live AI path) a Google Cloud project with Vertex AI
  enabled and `google-genai` credentials (see "Enable the AI core" below).

## 1. Local — deterministic (default, no credentials)
```bash
git clone https://github.com/asifdotpy/forge-mind.git
cd forge-mind
uv sync                      # installs runtime + dev deps (incl. google-genai)
uv run pytest tests/         # 231 passed, 1 skipped (live-token-gated)

# Black-box fixture run (all 7 fixtures, 0 errors)
PYTHONPATH=src uv run python scripts/run_fixture.py

# Run the API locally
PYTHONPATH=src uv run uvicorn forgemind.api:create_api --factory --reload
# open http://127.0.0.1:8000/  -> M3 judge-visible surface (provenance,
# validation, uncertainty, human control)
```

## 2. Local — ADK + Gemini path (optional, needs Vertex creds)
```bash
export VERTEX_PROJECT=<your-gcp-project-id>     # or GOOGLE_CLOUD_PROJECT
export GOOGLE_API_KEY=<vertex-api-key>          # or use ADC:
# gcloud auth application-default login
export FORGEMIND_RUNTIME=adk

PYTHONPATH=src uv run uvicorn forgemind.api:create_api --factory
curl -X POST http://127.0.0.1:8000/api/v1/events \
  -H 'content-type: application/json' \
  -d @fixtures/inputs/FIXTURE-001-happy-path.json
# response includes m3_proof + (with creds) Gemini-backed worker observations
```
- `FORGEMIND_RUNTIME` unset or `deterministic` → existing deterministic
  pipeline (231 tests stay green, no GenAI import at runtime).
- Only `FORGEMIND_RUNTIME=adk` activates the ADK workflow + human-approval gate.

## 3. Deploy to Google Cloud (M2 — Cloud Run)
The repo already deployed `forgemind-v3-prod` (us-central1). To redeploy with
the M3-B AI core:
```bash
# 1) Ensure google-genai is in the image. It is already a [project].dependency
#    and pinned in uv.lock, so `uv sync --frozen --no-dev` in the Dockerfile
#    installs it. No Dockerfile change required.
# 2) Set runtime env on the Cloud Run service:
#    FORGEMIND_RUNTIME=adk, VERTEX_PROJECT=<id>, GOOGLE_API_KEY=<key>
#    (use Secret Manager / Workload Identity — never commit keys)
gcloud run deploy forgemind-v3-prod \
  --region us-central1 --image <artifact-registry-image> \
  --set-env-vars FORGEMIND_RUNTIME=adk \
  --update-secrets VERTEX_PROJECT=vertex-project:latest,GOOGLE_API_KEY=gemini-key:latest \
  --allow-unauthenticated
# verify: curl -X POST .../api/v1/events with FIXTURE-001
# scale to zero after the demo: gcloud run services update forgemind-v3-prod --no-traffic
```
Full scripts: `deploy/cloudbuild.yaml`, `deploy/deploy.sh`.

## 4. Verify the judge surface
- `GET /api/v1/situations/{situation_id}` → the four M3 proof blocks.
- `GET /` → HTML viewer showing provenance, validation, uncertainty,
  human-control for the default situation.

## Security notes
- No secrets are committed; `ggshield` pre-commit + `tests/test_secret_handling.py`
  guard the repo.
- ChromaDB is dev-only (ADR-009) and absent from the production image.
