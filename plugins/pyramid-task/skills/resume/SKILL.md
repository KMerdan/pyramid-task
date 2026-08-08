---
name: resume
description: Resume a paused Pyramid Task V3 executable node from its canonical handoff and receive an enriched agent packet. Use when returning from a break, continuing a prior session, or accepting an explicit task handoff without bypassing ownership, graph, assurance, or worktree checks.
---

# Resume a Pyramid Task

Read `../../references/handoff-contract.md`. Load `../../references/agent-contracts.md` only for ownership edge cases, `../../references/brownfield-assurance.md` only when drift includes assurance, and `../../references/lifecycle-contract.md` only if the plan is inactive.

## Workflow

1. Inspect the compact paused frontier when the task is not explicit. Reuse its graph version and context ID for the resume guard:

```bash
python3 ../../scripts/pyramid.py inspect --project <project-root> --paused --json
python3 ../../scripts/pyramid.py lifecycle --project <project-root> --json
```

2. Resume the selected node. The runtime finds the active handoff from canonical state, validates plan/task identity, checks the graph, baseline, assurance, and source-worktree fingerprints, acquires a new lease, and emits `task.resumed`.

```bash
python3 ../../scripts/pyramid.py resume \
  --project <project-root> --node TASK-203 --actor <actor> \
  --lease-minutes 120 \
  --expected-version <graph-version> --expected-context <context-id> --json
```

3. Read the returned handoff-enriched task packet before changing files. Start with `recommended_first_action`, then reconcile changed files, checks, decisions, blockers, risks, and required context.
4. If the runtime returns `stale-handoff`, inspect the reported differences. Do not continue merely because the original work looked safe. Reconcile the changed graph, assurance, or worktree first. Only after reviewing them may the user or authorized agent explicitly choose `--accept-stale`.
5. A different actor may resume `handoff` mode immediately. A `hold` belongs to the pausing actor until its deadline; another actor must wait for expiry and use `--takeover`.

## Boundaries

- Never reconstruct continuation context from chat memory when a canonical handoff exists.
- Never edit the immutable handoff record to make it appear current.
- Do not use `take` on a paused node; resume is the only transition that consumes its active handoff.
- Resume returns the task to `working`; record completion, blockers, or release later through `pyramid-task:update`.
