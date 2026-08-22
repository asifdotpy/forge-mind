# Specifications (docs/specs/)

> **⚠️ Location change (2026-08-22):** Canonical specifications now live in **`specs/<feature>/`** at the repository root, following the Spec-Kit convention (e.g. `specs/001-hierarchical-runtime-dag/`). This directory retains only legacy pointers (see [`SPEC-001.md`](SPEC-001.md)) and this lifecycle note.

This directory contains formal feature and component specifications for ForgeMind.

## Specification Lifecycle
1. **Draft**: Spec written, open questions and contracts being finalized.
2. **Approved**: User/Team approved, ready for implementation.
3. **In Progress**: Active tests and implementation being built.
4. **Verified**: Implementation passes tests, application runs, black-box verification succeeds.
5. **Superseded**: Replaced by a newer specification.

## Spec Template (`SPEC-XXX.md`)
Each specification must follow this structure:
```markdown
# SPEC-XXX: [Feature / Component Name]

## Status: [Draft | Approved | In Progress | Verified | Superseded]

## 1. Overview & Purpose
What problem does this solve and why is it needed?

## 2. Inputs & Preconditions
What data, configuration, or state must be present?

## 3. Outputs & Public Contract
API endpoints, data schemas, or interface definitions.

## 4. Acceptance Criteria
- [ ] Criterion 1
- [ ] Criterion 2

## 5. Verification Plan
- Automated test command: `pytest tests/...`
- Black-box verification command: `curl ...`
```
