---
name: take
description: Claim a ready executable node from a Pyramid Task V3 project and receive a compact agent task packet with brownfield impact and inspection context. Use when an implementation or research agent is about to begin a specific task or needs the next safe ready task without duplicating another agent's work.
---

# Take a Pyramid Task

Use the compact ready frontier first. Load `../../references/agent-contracts.md` only for ownership or packet-contract questions, `../../references/brownfield-assurance.md` only when the selected packet contains assurance, and `../../references/lifecycle-contract.md` only if the plan is inactive.

## Workflow

1. Identify the project root and stable actor name.
2. Inspect the compact ready frontier if the user did not specify a node. Reuse the selected task's `mutation_guard`; it excludes unrelated inspection refreshes while binding the task contract, dependency state, baseline, and impact map. Do not load full packets for every candidate. The frontier includes `needs-rework` nodes and prioritizes them before new work.
3. Claim exactly one task:

```bash
python3 ../../scripts/pyramid.py take --project <project-root> --node TASK-203 --actor <actor> --expected-guard <task-guard> --json
python3 ../../scripts/pyramid.py take --project <project-root> --next --actor <actor> --expected-version <graph-version> --expected-context <context-id> --json
```

4. Read only the packet's required context plus files needed to perform the task.
5. If repository evidence shows that the task contains multiple independently reviewable work units or needs a composition gate, do not silently improvise a subtree. Release the claim and use `pyramid-task:expand`; otherwise continue without asking the user about expansion.
6. Respect `allowed_write_scope`, non-goals, dependencies, evidence requirements, affected assets, inspections, and assurance blockers. A task may be executable while its future audit remains assurance-blocked; resolve the evidence gap rather than hiding it.
7. If the request includes implementation, perform the task and finish through the `update` interface. Otherwise return the claimed packet.

## Boundaries

- Never claim work for a read-only status request.
- Never bypass a locked dependency.
- Never work from a stale task guard. A global graph version may advance for unrelated evidence; refresh only the selected packet when its scoped guard conflicts.
- Never take a paused task. Use `pyramid-task:resume` so the canonical handoff is checked and returned.
- Release the claim if the task will not be attempted.
- Never take work from a completed or archived plan. Reopen or restore it through lifecycle first.
