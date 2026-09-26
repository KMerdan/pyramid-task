---
name: orchestrate
description: Coordinate multiple ready Pyramid Task nodes with sub-agents when the host supports parallel agents. Use when the user asks to run independent tasks concurrently, speed up a ready wave, delegate safe work, or determine which ready tasks can execute together without dependency, file-scope, generated-output, asset, assurance, or drift conflicts.
---

# Orchestrate Pyramid Tasks

Derive one safe parallel batch from current canonical state, give each worker only its exact task packet, and rejoin through the graph's audit boundary. The runtime recommends batches; the host agent decides whether and how to spawn sub-agents.

For harness-enabled packets, use `../../references/development-harness.md` when collecting or joining proof. Revalidate executor/helper input fingerprints against the integrated candidate before acceptance. Shared setup may enable several branches; serialize only true prerequisites. Reuse valid shared runs and perform distinct composition checks once at the joint boundary.

## Context routing

Read `../../references/parallel-execution.md` before coordinating a batch and `../../references/intra-task-helpers.md` before using spare slots inside a claimed task. Read `../../references/demonstrable-increments.md` when a selected join is an increment gate. Read `../../references/agent-contracts.md` only when constructing worker prompts or resolving a guard conflict. Read `../../references/brownfield-assurance.md` only when the frontier names shared inspections or an assurance blocker.

## Workflow

1. Locate the project and validate it:

```bash
python3 ../../scripts/pyramid.py validate --project <project-root> --json
```

2. Query the current derived frontier with the total available agent slots, including the coordinator:

```bash
python3 ../../scripts/pyramid.py inspect --project <project-root> --parallel-ready --max-agents <slots> --json
```

3. Select the first returned group. Groups are ordered by earliest wave, highest slot use, then stable ID. A group is a scheduling result, not a demonstrable increment. Never infer safety from level, workstream, or ready status alone, and never merge runtime groups. If no group exists, continue serially and report the returned reasons.
4. Establish one canonical runtime and integration root containing the authoritative `.pyramid`. Before claiming anything, verify that the host can provide a separate code worktree for every source-writing task and a reliable patch or commit integration path. If it cannot, execute the group serially. Workers never mutate Pyramid state inside their worktrees.
5. Give every task a stable actor. From the canonical root, the coordinator claims the selected tasks sequentially with each frontier `claim_guard`. Save the complete packet and replace the claim guard with `packet.mutation_guards.task` returned by `take`; that refreshed guard is required for update, pause, or release. If any claim fails, spawn no workers, release every successful claim with its post-`take` guard, and derive a fresh frontier.
6. Keep one task with the coordinator and reserve graph-task workers before any helper. Spawn no more than `recommended_subagents` graph-task workers. Send each executor only its claimed packet, actor, isolated code-worktree path, and saved join metadata. Workers edit and test code, then return a scoped patch or commit plus an `agent-result-v1` draft. They do not run `take`, `update`, topology, lifecycle, assurance, or audit commands.
7. Maintain one global slot ledger. After graph-task reservations, use remaining host slots for useful `helper-job-v1` research, reconnaissance, review, or validation jobs inside the coordinator's retained task. Helpers are read-only, snapshot-bound, bounded, and ephemeral. A worker may request help but may not spawn an untracked nested agent; only the coordinator reserves and issues helper jobs.
8. Keep the canonical root clean enough to integrate. As workers and helpers finish, reconcile helper results at their declared join boundaries, verify actual worker paths and assets against their packets, integrate disjoint patches one at a time, and submit each terminal update from the canonical root using that task's post-`take` guard. Stop if integration reveals overlap, unexpected generated output, scope drift, or a dependency change.
9. Before interrupting a worker, preserve its patch and evidence, then use the current task guard to `pause`, mark `blocked`, or `release` the canonical claim as appropriate. Never strand a working claim until lease expiry. Do not run the batch join unless every selected task reached `implemented` and its code was integrated.
10. Keep the original group's join metadata; implemented tasks disappear from the ready frontier. `shared_inspections.refresh_policy` records planned scheduling, while `effective_refresh_boundary` accounts for mandatory audit freshness. Refresh the listed records once after all group implementations at that effective boundary, then treat each `inspect --audit-readiness` result as authoritative and refresh any minimal blocker it still names. Independently audit each implemented task. After prerequisite task audits pass, query and run the saved `join_gate` when present. If that gate establishes a demonstrable increment, require its meaningful scenario and inherited proofs; batch completion alone is insufficient. If an audit or integration fails, repair only the affected task or joint claim.
11. Derive a fresh parallel frontier only after the batch audits finish. Repeat when the user requested all safe work.

## Worker prompt contract

Include:

- exact claimed packet, actor, and isolated code-worktree path;
- an explicit statement that the coordinator owns canonical `.pyramid` mutations;
- a requirement to obey the returned packet's write scope, assets, inspections, commands, evidence, and non-goals;
- a requirement to return a scoped patch or commit and an `agent-result-v1` draft to the coordinator;
- a requirement to report unexpected scope before writing it;
- the join gate and an instruction not to perform it independently.

Do not include unrelated packets, full assurance detail, all event files, or guessed implementation instructions.

## Boundaries

- Treat parallel groups as disposable read-only recommendations. Recompute them after relevant state changes; never persist them in `plan.json` or `state.json`.
- Treat intra-task helpers as disposable execution aids, not graph tasks, events, owners, guards, or independent completion claims.
- Same level does not mean independent. Same wave is necessary but not sufficient.
- A successful parallel batch does not establish a runnable or demonstrable increment; only its declared increment gate can do that.
- Do not spawn more workers than available isolated workspaces, host concurrency slots, or the runtime recommendation.
- Reserve selected graph-task workers before helpers. Count the coordinator, every graph worker, and every helper once in the same host-capacity ledger.
- Use only one canonical runtime root. Never let isolated worktrees fork `.pyramid` state or let workers mutate topology, lifecycle, assurance, or audit records.
- Do not claim parallel source execution when the host lacks sub-agents, isolated workspaces, or a safe integration path; use the same group order serially.
- A frontier guard is claim-only. Use the refreshed task guard returned by `take` for every later mutation. A global graph version advancing for an unrelated task is not a worker conflict.
