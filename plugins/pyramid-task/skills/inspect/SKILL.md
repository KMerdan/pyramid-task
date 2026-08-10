---
name: inspect
description: Inspect an existing Pyramid Task V3 or compatible legacy project without changing it. Use when an agent or a human needs status, ready or paused work, conflict-safe parallel batches, handoff identity, blockers, pending audits, baseline and impact coverage, stale inspections, scope drift, evidence gaps, task details, or the trace from a node to the final intent.
---

# Inspect a Pyramid Task Plan

Start with the smallest runtime query. Load `../../references/graph-contract.md` only for topology, `../../references/agent-contracts.md` only for one detailed node, `../../references/handoff-contract.md` only for paused work, `../../references/brownfield-assurance.md` only when assurance is present, and `../../references/lifecycle-contract.md` only for lifecycle questions.

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
python3 ../../scripts/pyramid.py inspect --project <project-root> --parallel-ready --max-agents 4 --json
python3 ../../scripts/pyramid.py inspect --project <project-root> --blocked --json
python3 ../../scripts/pyramid.py inspect --project <project-root> --pending-audits --json
python3 ../../scripts/pyramid.py inspect --project <project-root> --audit-readiness GATE-205 --json
python3 ../../scripts/pyramid.py inspect --project <project-root> --paused --json
python3 ../../scripts/pyramid.py inspect --project <project-root> --node TASK-203 --json
python3 ../../scripts/pyramid.py inspect --project <project-root> --assurance-summary --json
python3 ../../scripts/pyramid.py inspect --project <project-root> --assurance --json
python3 ../../scripts/pyramid.py inspect --project <project-root> --assurance-detail --json
python3 ../../scripts/pyramid.py diff --project <project-root> --from-version <version> --json
python3 ../../scripts/pyramid.py lifecycle --project <project-root> --json
```

Use `--assurance-detail` only for individual assurance records and `diff --detail` only when compact changed-field summaries are insufficient. Use the returned task or audit mutation guard for scoped work; reserve the global context identity for topology, lifecycle, and full assurance mutations.

Use `--parallel-ready` when the question is which ready tasks can safely run together. Its groups are derived from the current wave, dependency, write/generated scope, asset, inspection-policy, and drift state; they are not stored graph versions. Route actual multi-agent execution through `pyramid-task:orchestrate`.

4. Explain derived facts with causes: unmet dependencies for `locked`, ownership for working tasks, handoff mode and deadline for paused tasks, failed checks, assurance blockers, stale evidence, open drift, and material findings.
5. Distinguish `implemented` from `verified`, task readiness from assurance readiness, and node completion from plan closure. Report labeled coverage counts, not an invented percentage.

## Boundaries

- Keep this interface read-only.
- Do not infer readiness from Markdown prose when the runtime supplies derived availability.
- Do not load the entire graph when one node packet answers the request.
- Do not read every event file to explain recent changes; use the bounded diff query.
- Surface validation failures before summarizing status.
