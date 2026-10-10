---
name: take
description: Claim one ready implementation or research task in Pyramid Task V3 and receive its scoped agent packet. Use before beginning work; use inspect for read-only status and resume for paused work.
---

# Take a Pyramid Task

Use the compact ready frontier first. Load `../../references/agent-contracts.md` only for ownership or packet-contract questions, `../../references/brownfield-assurance.md` only when the selected packet contains assurance, and `../../references/lifecycle-contract.md` only if the plan is inactive.

Consider a read-only helper for an independent repository/dependency question, test discovery, or review of a frozen candidate when it can resolve uncertainty or shorten the remaining work. Weigh that benefit against duplicated context and coordination cost. Check authorization and capacity, then read `../../references/intra-task-helpers.md` before deciding or spawning. Continue serially when those conditions are absent. A dependency investigation independent of the current edit may qualify; reading one known file does not.

When the packet has `harness`, reuse the current contract or read the relevant section of `../../references/development-harness.md` if it is missing. Capture `inspect --harness <node>` before checks and use valid reusable runs first. Establish only missing observation capability required by the task, using project-fit probes and browser tooling. Do not install a generic test stack or make independent product work wait unnecessarily.

## Workflow

1. Identify the project root and stable actor name.
2. Inspect the compact ready frontier if the user did not specify a node. Reuse the selected task's `mutation_guard`; it excludes unrelated inspection refreshes while binding the task contract, dependency state, baseline, and impact map. Do not load full packets for every candidate. The frontier includes `needs-rework` nodes and prioritizes them before new work.
   When coordinating multiple graph tasks, use `pyramid-task:orchestrate` and claim only a task returned in the selected parallel group. Intra-task helpers remain children of this one claimed task and follow `intra-task-helpers.md`.
3. Claim exactly one task:

```bash
python3 ../../scripts/pyramid.py take --project <project-root> --node TASK-203 --actor <actor> --expected-guard <task-guard> --json
python3 ../../scripts/pyramid.py take --project <project-root> --next --actor <actor> --expected-version <graph-version> --expected-context <context-id> --json
```

4. Read only the packet's required context plus implementation, matching checks and dependencies needed for the change. Execute bundled commands without preloading their Python implementation. Resolve command paths from this skill's directory, then invoke the absolute script path with the explicit project root. Reuse the packet while its scoped guard remains valid; do not reload the full graph or historical reports on every action. For an additive file/context discovery inside an unchanged outcome, use `amend` through `../../references/task-amendments.md` before writing outside scope.
5. If repository evidence shows that the task contains multiple independently reviewable work units or needs a composition gate, do not silently improvise a subtree. Release the claim and use `pyramid-task:expand`; otherwise continue without asking the user about expansion.
6. Before choosing an eligible helper, read `intra-task-helpers.md`'s Eligibility and Phases and freshness sections. If selected, follow its job, result and slot contracts for immutable snapshots, bounded work, isolation and evidence reconciliation.
7. Respect `allowed_write_scope`, non-goals, dependencies, evidence requirements, affected assets, inspections, and assurance blockers. Helpers never write source or mutate `.pyramid`; the task owner remains responsible for the result.
8. If the request includes implementation, perform the task and finish through the `update` interface. Otherwise return the claimed packet.

## Boundaries

- Never claim work for a read-only status request.
- Never bypass a locked dependency.
- Never work from a stale task guard. A global graph version may advance for unrelated evidence; refresh only the selected packet when its scoped guard conflicts.
- Keep the current guard as invocation data, not a literal in reviewed procedure source. For a custom caller or guard conflict, read the two-identity recipe in `../../references/agent-contracts.md`; host permission and proof freshness remain separate.
- Never assume a check is read-only. Tests and builds may create caches, generated artifacts, databases, or snapshots; isolate them from the canonical worktree.
- Never take a paused task. Use `pyramid-task:resume` so the canonical handoff is checked and returned.
- Release the claim if the task will not be attempted.
- If a check is blocked, preserve its failed/missing evidence and exact pending need. Continue the next authorized dependency-safe slice; do not repeatedly ask unchanged routine questions or clear the blocked claim to continue.
- Never take work from a completed or archived plan. Reopen or restore it through lifecycle first.
