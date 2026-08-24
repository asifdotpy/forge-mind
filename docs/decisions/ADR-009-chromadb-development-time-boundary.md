# ADR-009: ChromaDB Is a Development-Time Derived Index

## Status
Accepted (2026-08-24)

## Context
ForgeMind maintains a local Knowledge Brain: a ChromaDB vector index built from the boundary-scoped ForgeMind Notion knowledge base (30 pages, 368 chunks). It gives SpecForge semantic grounding for planning, consistency review, and cross-session continuity.

An audit of that dependency surfaced two defects:

1. **Packaging**: `chromadb` was declared in `[project].dependencies`, so `uv sync --frozen --no-dev` installed it into the production Cloud Run image even though no runtime tier ever imports it (`src/forgemind/` contains zero `chroma` references; `import forgemind` succeeds with `chromadb` blocked; 117 contract+integration tests pass under an import block). The pinned version carries CVE-2026-45829 (CRITICAL, no fixed release published), and `cloudbuild.yaml` deploys the image `--allow-unauthenticated` — an unreachable CVE sitting on an internet-facing service. FAIL-004 (`docs/FAILURE_LOG.md`) documents why no satisfying version bump exists.
2. **Test coupling**: `tests/test_secret_handling.py` — the FAIL-003 security regression guard — failed without chromadb solely because it executes `scripts/sync_notion_brain.py`, whose module-level `import chromadb` was unrelated to what those tests exercise; `tests/test_knowledge_brain.py` errored at collection instead of skipping cleanly.

The principle that resolves both:

> **ChromaDB provides CONTEXT. It does not provide AUTHORITY.**

ChromaDB is a derived semantic index over boundary-scoped Notion knowledge, consumed only by SpecForge for planning, grounding, consistency review, and cross-session continuity. Notion remains the authoritative human-facing architecture/ADR source. Retrieved memory is never automatically authoritative: on conflict the Truth Hierarchy governs — ADR > specification > implementation > verified tests > project memory — and a retrieved memory contradicting current SPEC-001 is a drift signal to report, not a decision input.

## Decision
1. Classify ChromaDB as a **development-time dependency** (`[dependency-groups].dev`). It MUST NOT be a runtime dependency: no runtime tier may read from or write to it, and it is excluded from the production image.
2. Exclude dev-time Knowledge Brain tooling (`scripts/sync_notion_brain.py`, `scripts/query_brain.py`) from the production image; mark Knowledge Brain tests with the registered `brain` marker so they skip cleanly when the index or chromadb is absent.
3. Enforce the boundary mechanically via `tests/contract/test_runtime_boundary.py`.
4. Runtime ChromaDB integration is **DEFERRED to post-M3**; introducing it requires a new ADR.

## Alternatives Considered
- Option (a): Wire ChromaDB into the runtime to resolve documentation drift — rejected: solves a packaging defect with an architectural change; would create an accidental 6th state layer, add an unpatched CRITICAL CVE to a network-exposed service, and make deterministic tiers depend on mutable, non-deterministic retrieval (violates ADR-007 determinism).
- Option (b): Remove ChromaDB entirely — rejected: destroys SpecForge cross-session continuity.
- Option (c): Keep it as an unused runtime dependency — rejected: status quo; ships an unreachable CRITICAL CVE and leaves docs and packaging in permanent conflict.

## Consequences
- **Positive**: Production image drops chromadb plus its transitive tree (onnxruntime, tokenizers, numpy, grpcio, kubernetes); CVE-2026-45829 leaves the production attack surface; deterministic tests run on a bare clone (CI/CD viable); packaging/docs conflict ends.
- **Negative / Trade-offs**: SpecForge grounding requires the dev dependency group; runtime engineering memory is unavailable to workers (accepted, deferred to post-M3).

## Related
- ADR-001: supersedes its "Shared Knowledge & State" row by removing "Local ChromaDB".
- ADR-002: single-deployable MVP container boundary unchanged.
- ADR-007: determinism constraint cited above.
- FAIL-004 (`docs/FAILURE_LOG.md`): the version-constraint freeze motivating reclassification over upgrade.
