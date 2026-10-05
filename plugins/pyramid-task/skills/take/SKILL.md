---
name: take
description: Claim a ready executable node from a Pyramid Task V3 project and receive a compact agent task packet with brownfield impact and inspection context. Use when an implementation or research agent is about to begin a specific task or needs the next safe ready task without duplicating another agent's work.
---

# Take a Pyramid Task

Use the compact ready frontier first. Load `../../references/agent-contracts.md` only for ownership or packet-contract questions, `../../references/intra-task-helpers.md` when the host has sub-agents and spare slots, `../../references/brownfield-assurance.md` only when the selected packet contains assurance, and `../../references/lifecycle-contract.md` only if the plan is inactive.

When the packet has `harness`, read `../../references/development-harness.md`. Establish only missing observation capability required by the task, using project-fit probes and browser tooling. Before new checks, capture `inspect --harness <node>`; reuse a valid run when it proves the actual claim. Do not install a generic test stack or make independent product work wait unnecessarily.

## Workflow

1. Identify the project root and stable actor name.
2. Inspect the compact ready frontier if the user did not specify a node. Reuse the selected task's `mutation_guard`; it excludes unrelated inspection refreshes while binding the task contract, dependency state, baseline, and impact map. Do not load full packets for every candidate. The frontier includes `needs-rework` nodes and prioritizes them before new work.
   When coordinating multiple graph tasks, use `pyramid-task:orchestrate` and claim only a task returned in the selected parallel group. Intra-task helpers remain children of this one claimed task and follow `intra-task-helpers.md`.
3. Claim exactly one task:

```bash
python3 ../../scripts/pyramid.py take --project <project-root> --node TASK-203 --actor <actor> --expected-guard <task-guard> --json
python3 ../../scripts/pyramid.py take --project <project-root> --next --actor <actor> --expected-version <graph-version> --expected-context <context-id> --json
```

4. Read only the packet's required context plus files needed to perform the task. Reuse that packet while its scoped guard remains valid; do not reload the full graph or historical reports on every action. For an additive file/context discovery inside an unchanged outcome, use `amend` through `../../references/task-amendments.md` before writing outside scope.
   A selected `inspect --node` may summarize harness details; use `--harness` for capture or `--node --full` for missing procedure detail. Mandatory skill reads remain mandatory; supporting references need reopening only when missing, changed or relevant to a new decision.
5. If repository evidence shows that the task contains multiple independently reviewable work units or needs a composition gate, do not silently improvise a subtree. Release the claim and use `pyramid-task:expand`; otherwise continue without asking the user about expansion.
6. For a bounded implementation task, calculate unreserved host slots after the coordinator and active graph-task workers. Graph tasks have priority. Delegate a useful independent research, reconnaissance, review, or validation question only when the expected benefit justifies duplicated context and coordination; spare slots alone are not a reason. Bound helper context and results using `helper-job-v1`. Do not delegate trivial reads or use a helper merely to appear parallel.
7. Bind each preflight helper to the current task guard plus an immutable base snapshot, narrow read scope, linked acceptance criteria, explicit questions, prohibitions, result budget, and join boundary. The guard is correlation context, not helper mutation authority. Continue only implementation that is independent of its open question, and reconcile the result before a load-bearing decision.
8. Freeze a candidate before delegating review or validation. Run commands that may write only in a disposable worktree or sandbox. Treat returned evidence as final only when its snapshot exactly matches the accepted candidate; otherwise mark it stale and rerun the minimal check.
9. Respect `allowed_write_scope`, non-goals, dependencies, evidence requirements, affected assets, inspections, and assurance blockers. Helpers never write source or mutate `.pyramid`; the task owner reconciles their bounded results and remains solely responsible for the parent result.
10. If the request includes implementation, perform the task and finish through the `update` interface. Otherwise return the claimed packet.

## Boundaries

- Never claim work for a read-only status request.
- Never bypass a locked dependency.
- Never work from a stale task guard. A global graph version may advance for unrelated evidence; refresh only the selected packet when its scoped guard conflicts.
- Keep the current guard as invocation data, not a literal in reviewed procedure source. For a custom caller or guard conflict, read the two-identity recipe in `../../references/agent-contracts.md`; host permission and proof freshness remain separate.
- Never assume a check is read-only. Tests and builds may create caches, generated artifacts, databases, or snapshots; isolate them from the canonical worktree.
- Never oversubscribe host capacity or let helpers spawn untracked nested agents. Reserve graph-task workers first and keep one coordinator-owned slot ledger.
- Never take a paused task. Use `pyramid-task:resume` so the canonical handoff is checked and returned.
- Release the claim if the task will not be attempted.
- If a check is blocked, preserve its failed/missing evidence and exact pending need. Continue the next authorized dependency-safe slice; do not repeatedly ask unchanged routine questions or clear the blocked claim to continue.
- Never take work from a completed or archived plan. Reopen or restore it through lifecycle first.
