# Failure Log & Institutional Memory

Every significant failure, unexpected error, or architectural mistake encountered during development must be documented here with its root cause, resolution, and future prevention rule.

---

### FAIL-001: Public SearXNG Rate Limiting & Bot Protection
- **Date**: 2026-08-17
- **Problem**: Programmatic JSON search queries to public SearXNG instances (e.g. `searx.tiekoetter.com`) failed with `HTTP 429: Too Many Requests`.
- **Root Cause**: Public SearXNG instances disable the `json` output format by default and employ anti-bot limiters to prevent unauthenticated scraping.
- **Resolution**: Pivoted to dedicated cloud AI search APIs (Tavily API, Exa API, DuckDuckGo) which provide reliable, structured JSON results without local hosting overhead.
- **Prevention**: Do not rely on unauthenticated public community scraper endpoints for core agent workflows; use managed developer API endpoints or self-hosted instances with explicitly enabled API formats.

---

### FAIL-002: Notion MCP Token Initialization
- **Date**: 2026-08-17
- **Problem**: Initial Notion MCP tool calls failed with `401: API token is invalid`.
- **Root Cause**: The MCP server configuration had an empty Bearer token placeholder in `OPENAPI_MCP_HEADERS`.
- **Resolution**: Updated the integration token in the MCP configuration and verified integration page permissions.
- **Prevention**: Verify integration tokens and permissions on both the client config and target Notion pages before executing MCP tools.

---

### FAIL-003: Hardcoded Notion Integration Token in Sync Script
- **Date**: 2026-08-22
- **Problem**: `scripts/sync_notion_brain.py` hardcoded a live Notion Integration Token v2 (`ntn_2721...wEgVu5HB`) as `DEFAULT_TOKEN`, used as a silent fallback by `get_notion_token()`. The secret was exposed in the source tree and reproducible in commit history.
- **Root Cause**: The credential was baked into the script instead of being injected at runtime, and no secret-scanning gate existed at commit time.
- **Resolution**:
  - Removed the hardcoded token; `get_notion_token()` now requires the `NOTION_TOKEN` env var and **fails fast** with a clear setup message when missing.
  - Added `.env.example` template (real `.env` stays gitignored).
  - Added a ggshield **pre-commit hook** (`.githooks/pre-commit`, wired via `git config core.hooksPath .githooks`) that blocks any commit containing a secret.
  - Added regression tests (`tests/test_secret_handling.py`) that detect the historical leak by SHA-256 digest and verify the fail-fast/read-env behaviour.
- **Prevention**: Secrets must never be committed. Tokens are read from the environment (`.env`, gitignored) only; the ggshield pre-commit hook enforces this before every commit; a full tree scan is verified with `ggshield secret scan path --recursive .`.

---

### FAIL-004: Dependabot Dependency Advisories (chromadb CRITICAL, cryptography HIGH×2/MODERATE)
- **Date**: 2026-08-23
- **Problem**: GitHub flagged 2 dependency vulnerabilities on `main`: `chromadb==1.5.9` → GHSA-f4j7-r4q5-qw2c / CVE-2026-45829 (**CRITICAL**, CVSS v4 network/pre-auth code injection in the Chroma server API, affected 1.0.0–1.5.9, **no fixed release published**) and `cryptography==48.0.1` → three advisories (GHSA-g6cj-pr64-35w5 **HIGH**, fixed 50.0.0; GHSA-jwv3-5hgf-82ww **HIGH**, fixed 49.0.0; GHSA-m2h6-j472-rp4c MODERATE, fixed 49.0.0).
- **Root Cause**: Transitive/direct pins trail upstream fixes. A `cryptography>=49/50` bump is structurally blocked because the latest `ggshield==1.53.0` (the repo-mandated secret-scanning gate from FAIL-003) declares `cryptography<49,>=43.0.1`; uv resolution fails for any higher pin while ggshield stays.
- **Resolution**: Risk **accepted with mitigation** (documented decision, MVP posture):
  - ForgeMind code never imports `cryptography` (verified by tree grep) — the vulnerable PKCS#7-decrypt and x509 chain-verification APIs are unreachable from this codebase.
  - chromadb is used exclusively in embedded mode (`chromadb.PersistentClient(path=...)` in `scripts/query_brain.py` / `scripts/sync_notion_brain.py`) — no Chroma HTTP server is ever run or exposed, so the pre-auth RCE endpoint has no network surface here.
  - `pyproject.toml` left untouched pending SpecForge review; no lock override applied since no satisfying version exists under current constraints.
- **Prevention**: Re-run the OSV/GitHub advisory sweep on every dependency refresh; bump `ggshield` beyond 1.53.0 as soon as a release lifts the `cryptography<49` cap (clears all three), and bump `chromadb` to the first patched release of CVE-2026-45829; keep Chroma in embedded client mode only — running a networked Chroma server is prohibited until the critical is patched.
