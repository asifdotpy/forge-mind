# Demo Video — Commands

## Setup

```bash
cd /home/asif1/forge-mind
.venv/bin/activate
export PYTHONPATH=src
```

## Export URL

```bash
export URL=https://forgemind-n3nupsii5a-uc.a.run.app
```

## Webhook Test — PR #210 (CI + Docs + Scripts)

```bash
curl -X POST "$URL/api/v1/adk/webhook" \
  -H 'Content-Type: application/json' \
  -d '{"action":"opened","number":210,"pull_request":{"number":210,"title":"docs(claims): reconcile scopes, add claim_lock.yml + claim-gate CI","created_at":"2026-08-30T10:00:00Z","head":{"sha":"48339440b44accb075d860df9d7426d6a871a75c"},"html_url":"https://github.com/thevertexagents/vertex-sentinel/pull/210","state":"open"},"repository":{"full_name":"thevertexagents/vertex-sentinel"},"sender":{"login":"asifdotpy"}}'
```

## Webhook Test — PR #204 (Dependabot CI only)

```bash
curl -X POST "$URL/api/v1/adk/webhook" \
  -H 'Content-Type: application/json' \
  -d '{"action":"opened","number":204,"pull_request":{"number":204,"title":"build(deps): bump actions/checkout from 4 to 7","created_at":"2026-08-30T10:00:00Z","head":{"sha":"4ba095829d0465f6431efc6eed8d44187736f541"},"html_url":"https://github.com/thevertexagents/vertex-sentinel/pull/204","state":"open"},"repository":{"full_name":"thevertexagents/vertex-sentinel"},"sender":{"login":"dependabot"}}'
```

## Test Suite

```bash
uv run pytest tests/
```

## Dashboard URLs

```
https://forgemind-n3nupsii5a-uc.a.run.app/view/SIT-GITHUB-210
https://forgemind-n3nupsii5a-uc.a.run.app/view/SIT-GITHUB-204
```

## Git History

```bash
git log --oneline -5
```
