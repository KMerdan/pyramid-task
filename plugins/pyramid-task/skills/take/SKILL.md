---
name: take
description: Claim a ready executable node from a Pyramid Task V2 project and receive a compact agent task packet. Use when an implementation or research agent is about to begin a specific task or needs the next safe ready task without duplicating another agent's work.
---

# Take a Pyramid Task

Read `../../references/agent-contracts.md` and `../../references/lifecycle-contract.md` completely before claiming work.

## Workflow

1. Identify the project root and stable actor name.
2. Inspect ready tasks if the user did not specify a node. The frontier includes `needs-rework` nodes and prioritizes them before new work.
3. Claim exactly one task:

```bash
python3 ../../scripts/pyramid.py take --project <project-root> --node TASK-203 --actor <actor> --json
python3 ../../scripts/pyramid.py take --project <project-root> --next --actor <actor> --json
```

4. Read only the packet's required context plus files needed to perform the task.
5. If repository evidence shows that the task contains multiple independently reviewable work units or needs a composition gate, do not silently improvise a subtree. Release the claim and use `pyramid-task:expand`; otherwise continue without asking the user about expansion.
6. Respect `allowed_write_scope`, non-goals, dependencies, and evidence requirements. Task metadata does not expand normal authorization.
7. If the request includes implementation, perform the task and finish through the `update` interface. Otherwise return the claimed packet.

## Boundaries

- Never claim work for a read-only status request.
- Never bypass a locked dependency.
- Never work from a stale packet after a graph-version conflict; inspect and take again.
- Release the claim if the task will not be attempted.
- Never take work from a completed or archived plan. Reopen or restore it through lifecycle first.
