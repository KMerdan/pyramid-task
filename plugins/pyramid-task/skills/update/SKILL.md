---
name: update
description: Record progress, blockers, risk, release, or implementation completion for a claimed Pyramid Task V3 node. Use when a worker agent must submit structured results, changed files and assets, and evidence without changing graph topology or declaring the parent outcome verified.
---

# Update a Pyramid Task

Read `../../references/agent-contracts.md` before creating a result. Load `../../references/brownfield-assurance.md` only when reporting changed assets or drift, and `../../references/lifecycle-contract.md` only if the plan is inactive.

## Workflow

1. Confirm the actor owns the active claim and the task packet is current.
2. Run the task's required checks. Record actual commands, outcomes, every changed file, known `changed_assets`, acceptance evidence, risks, and proposed graph changes in `agent-result-v1` JSON.
3. Apply exactly one transition using the graph version and context ID from the claimed task packet:

```bash
python3 ../../scripts/pyramid.py update --project <project-root> --node TASK-203 --actor <actor> --status implemented --result <result.json> --expected-version <graph-version> --expected-context <context-id> --json
python3 ../../scripts/pyramid.py update --project <project-root> --node TASK-203 --actor <actor> --status blocked --reason <reason> --result <result.json> --expected-version <graph-version> --expected-context <context-id> --json
python3 ../../scripts/pyramid.py update --project <project-root> --node TASK-203 --actor <actor> --status at-risk --reason <reason> --expected-version <graph-version> --expected-context <context-id> --json
python3 ../../scripts/pyramid.py update --project <project-root> --node TASK-203 --actor <actor> --status release --expected-version <graph-version> --expected-context <context-id> --json
```

4. Report execution, verification, health, availability, detected scope drift, invalidated assurance, and remaining rework separately.
5. If the agent discovered that the unchanged task contract needs internal decomposition, include `suggested_graph_changes`, release the claim, and use `expand`. Use `replan` when the contract or selected path changed.

## Boundaries

- `implemented` means the worker finished the scoped work; it does not mean `verified`.
- Do not report tests as passed unless they were run successfully.
- Do not hand-edit state, claims, graph snapshots, or event files.
- Do not use this interface to add, remove, or reparent nodes.
- Never omit an out-of-scope changed file to avoid drift detection. Reconcile drift through `pyramid-task:impact`.
