---
name: replan
description: Replan an existing Pyramid Task V2 graph from new evidence, audit failure, invalid assumptions, architecture changes, or an explicitly changed intent. Use when topology or path selection must change while preserving valid work, state history, and traceability.
---

# Replan a Pyramid Task Path

Read `../../references/pathfinder-workflow.md`, `../../references/graph-contract.md`, `../../references/agent-contracts.md`, and `../../references/lifecycle-contract.md` completely before changing topology.

Use `pyramid-task:expand` instead when a single executable task keeps the same purpose, contract, selected path, and external relations and only needs a deeper approved subtree.

## Workflow

1. Capture the triggering evidence or audit result.
2. Confirm the plan lifecycle is active. Restore an archived plan or reopen affected completed work before replanning.
3. Inspect affected nodes, descendants, alternatives, completed evidence, and the current graph version.
4. Preserve nodes and evidence that remain valid. Mark replaced paths `superseded`; never erase history.
5. Re-run backward and forward path checks across the affected region, expanding scope when a load-bearing assumption changes.
6. Write a complete candidate plan JSON.
7. Preview the diff:

```bash
python3 ../../scripts/pyramid.py replan --project <project-root> --plan <candidate-plan.json> --actor <actor> --reason <reason> --preview --json
```

8. Explain added, changed, superseded, and newly blocked or ready nodes. Obtain direction before a material intent change or scope expansion.
9. Apply the approved revision:

```bash
python3 ../../scripts/pyramid.py replan --project <project-root> --plan <candidate-plan.json> --actor <actor> --reason <reason> --apply --json
```

Use `--allow-intent-change` only when the user explicitly approved changing the final intent identifier.

## Boundaries

- Do not rewrite the plan through `update`.
- Do not invalidate verified work without citing the evidence or contract change that invalidates it.
- Do not delete rejected or superseded alternatives needed to explain plan history.
- Always preview before applying a material replan.
