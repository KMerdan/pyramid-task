---
name: update
description: Record progress, blockers, risk, release, or implementation completion for a claimed Pyramid Task V2 node. Use when a worker agent must submit structured results and evidence without changing graph topology or declaring the parent outcome verified.
---

# Update a Pyramid Task

Read `../../references/agent-contracts.md` and `../../references/lifecycle-contract.md` completely before preparing a result.

## Workflow

1. Confirm the actor owns the active claim and the task packet is current.
2. Run the task's required checks. Record actual commands, outcomes, changed files, acceptance-criterion evidence, risks, and proposed graph changes in an `agent-result-v1` JSON file.
3. Apply exactly one transition:

```bash
python3 ../../scripts/pyramid.py update --project <project-root> --node TASK-203 --actor <actor> --status implemented --result <result.json> --json
python3 ../../scripts/pyramid.py update --project <project-root> --node TASK-203 --actor <actor> --status blocked --reason <reason> --result <result.json> --json
python3 ../../scripts/pyramid.py update --project <project-root> --node TASK-203 --actor <actor> --status at-risk --reason <reason> --json
python3 ../../scripts/pyramid.py update --project <project-root> --node TASK-203 --actor <actor> --status release --json
```

4. Report the resulting execution, verification, health, availability, and any remaining rework state separately.
5. If the agent discovered that the unchanged task contract needs internal decomposition, include `suggested_graph_changes`, release the claim, and use `expand`. Use `replan` when the contract or selected path changed.

## Boundaries

- `implemented` means the worker finished the scoped work; it does not mean `verified`.
- Do not report tests as passed unless they were run successfully.
- Do not hand-edit state, claims, graph snapshots, or event files.
- Do not use this interface to add, remove, or reparent nodes.
