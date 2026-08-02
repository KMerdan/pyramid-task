---
name: inspect
description: Inspect an existing Pyramid Task V3 or compatible legacy project without changing it. Use when an agent or a human needs status, ready work, blockers, pending audits, baseline and impact coverage, stale inspections, scope drift, evidence gaps, task details, or the trace from a node to the final intent.
---

# Inspect a Pyramid Task Plan

Read `../../references/graph-contract.md`, `../../references/agent-contracts.md`, `../../references/brownfield-assurance.md`, and `../../references/lifecycle-contract.md` completely before interpreting a graph.

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
python3 ../../scripts/pyramid.py inspect --project <project-root> --assurance --json
python3 ../../scripts/pyramid.py lifecycle --project <project-root> --json
```

4. Explain derived facts with causes: unmet dependencies for `locked`, ownership for working tasks, failed checks, assurance blockers, stale evidence, open drift, and material findings.
5. Distinguish `implemented` from `verified`, task readiness from assurance readiness, and node completion from plan closure. Report labeled coverage counts, not an invented percentage.

## Boundaries

- Keep this interface read-only.
- Do not infer readiness from Markdown prose when the runtime supplies derived availability.
- Do not load the entire graph when one node packet answers the request.
- Surface validation failures before summarizing status.
