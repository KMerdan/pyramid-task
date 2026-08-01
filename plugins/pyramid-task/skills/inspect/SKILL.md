---
name: inspect
description: Inspect an existing Pyramid Task V2 project without changing it. Use when Codex or a human needs status, ready work, blockers, pending audits, evidence gaps, task details, dependency explanations, or the trace from a node to the final intent.
---

# Inspect a Pyramid Task Plan

Read `../../references/graph-contract.md`, `../../references/agent-contracts.md`, and `../../references/lifecycle-contract.md` completely before interpreting a graph.

## Workflow

1. Locate `<project-root>/.pyramid/plan.json`.
2. Run validation before relying on derived state:

```bash
python3 ../../scripts/pyramid.py validate --project <project-root> --json
```

3. Use the smallest query that answers the request:

```bash
python3 ../../scripts/pyramid.py inspect --project <project-root> --summary --json
python3 ../../scripts/pyramid.py inspect --project <project-root> --ready --json
python3 ../../scripts/pyramid.py inspect --project <project-root> --blocked --json
python3 ../../scripts/pyramid.py inspect --project <project-root> --pending-audits --json
python3 ../../scripts/pyramid.py inspect --project <project-root> --node TASK-203 --json
python3 ../../scripts/pyramid.py lifecycle --project <project-root> --json
```

4. Explain derived facts with their causes: list unmet dependencies for `locked`, ownership for `claimed`, and failed checks for `blocked` or verification failure.
5. Distinguish `implemented` from `verified`, and node completion from plan closure. Report progress as verified coverage, lifecycle, and frontier state, not an invented percentage.

## Boundaries

- Keep this interface read-only.
- Do not infer readiness from Markdown prose when the runtime supplies derived availability.
- Do not load the entire graph when one node packet answers the request.
- Surface validation failures before summarizing status.
