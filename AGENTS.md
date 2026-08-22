# ForgeMind Agent Instructions

## Before modifying code

1. Read docs/CURRENT_STATE.md
2. Identify the relevant SPEC in `specs/<feature>/` (canonical; e.g. `specs/001-hierarchical-runtime-dag/`). Legacy pointers live in `docs/specs/`.
3. Check docs/ARCHITECTURE.md for component boundaries.
4. Do not guess unresolved architectural decisions (check docs/decisions/).

## Implementation

- Work only within the task scope.
- Prefer small changes.
- Do not introduce unnecessary dependencies.
- Do not change unrelated files.

## Verification

A task is not complete until:

1. Relevant tests pass.
2. Application starts.
3. Black-box verification succeeds.
4. Expected output matches the specification.

## Documentation

After successful verification:

- Update docs/CURRENT_STATE.md.
- Update SPEC status.
- Record significant failures in docs/FAILURE_LOG.md.

## Escalation

Stop and ask when:

- The specification conflicts with architecture.
- An architectural decision is missing.
- The task requires changing a public contract.

## Directory Boundaries & Safety

- **Scope Limit**: You must NEVER create, edit, or delete files outside of the project workspace (`/home/asif1/forge-mind`).
- **File Access**: All file modifications must be strictly confined to this repository.
- **Commands**: Terminal commands must execute strictly with their working directory inside the project root. Do not run commands targeting external directories.
- **Escalation**: If a task requires modifying files outside this directory, stop immediately and ask for explicit user permission.

