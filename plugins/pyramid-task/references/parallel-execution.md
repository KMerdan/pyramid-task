# Parallel Execution Contract

Pyramid treats parallelism as a live scheduling query, not canonical plan state. `inspect --parallel-ready` derives deterministic groups from the current ready frontier and returns no mutation. Re-run it whenever task, dependency, scope, drift, or assurance state changes.

## Safety model

Tasks may share a group only when all of these are true:

- both are currently `ready` or `needs-rework`;
- both are in the same execution wave;
- no direct or transitive start or audit dependency couples them;
- declared write, evidence, and generated-output patterns do not overlap;
- neither task has a broad write scope, a missing scope for a writing effect, or open scope drift;
- affected assets do not overlap, unless every common inspection has a batchable `per-wave`, `pre-audit`, or `release` refresh policy.

`level` describes distance from the intent. `wave` describes earliest safe execution time. Neither field alone proves conflict freedom, so the runtime also evaluates dependencies, scopes, generated outputs, assets, inspections, and drift.

The analysis is conservative. Missing asset coverage, missing refresh policy, `per-change` inspection policy, broad scope, or unknown overlap keeps work serial.

## Frontier output

Each group contains:

- a deterministic group ID and same-wave task IDs;
- recommended total agents and sub-agents;
- required isolation mode;
- compact task records with claim-only guards, scopes, assets, and inspections;
- shared assets and per-inspection planned refresh policies, plus the effective boundary required before group audits;
- the nearest common audit gate, when one exists.

`serial_tasks` explains why a candidate was not grouped. `conflicts` reports pairwise dependency, scope, or assurance conflicts. These are scheduling facts, not additional graph versions. Groups are ordered by wave ascending, agent utilization descending, then stable group ID.

## Coordinator and worker ownership

One coordinator owns the authoritative project root, group selection, sub-agent lifecycle, all canonical Pyramid mutations, patch integration, shared assurance refreshes, and the join audit. Each executor owns exactly one task and uses an isolated code worktree for source-writing work. The canonical root is the only place where `.pyramid` is mutated.

The coordinator uses each group guard once to claim its exact task from the canonical root. `take` changes that task state, so its returned `packet.mutation_guards.task` replaces the frontier guard for all later update, pause, or release mutations. Task guards deliberately exclude unrelated task state and unrelated inspection timestamps, so another valid claim does not create a false conflict. If a later batch claim fails, release all earlier successful claims with their refreshed guards before deriving another frontier.

The coordinator sends the claimed packet to the executor. The executor reads and edits only its code worktree, then returns a patch or commit and an `agent-result-v1` draft. The coordinator verifies scope, integrates patches into the canonical root one at a time, and records updates there. Worktree-local runtime mutations are forbidden because they would fork canonical state.

Unexpected paths, generated files, assets, dependencies, or merge conflicts stop the affected batch. Preserve partial work and transition the canonical claim to paused, blocked, or released before interrupting its worker. Do not hide drift by broadening the result after implementation.

Save the selected group's join metadata before execution. After all patches are integrated and every task is `implemented`, refresh shared inspections at `effective_refresh_boundary`: `per-wave` when any inspection requires it, otherwise before the covered task audits. The individual `refresh_policy` remains planning intent; it never waives the runtime's freshness rule. Always use fresh audit readiness and refresh any minimal blocker it names, including a release-planned inspection when an earlier covered audit requires it. Audit each task independently, then run the saved common join gate after its prerequisites pass. Recompute the parallel frontier only after this boundary. A task failure invalidates only the smallest affected claims; unrelated completed work remains reusable.

## Planning for useful parallelism

During create, expand, or replan:

- split work by independently reviewable outcomes, not arbitrary file counts;
- minimize hard dependencies and use them only for real ordering constraints;
- assign independent branches the same earliest safe wave;
- declare narrow, non-overlapping write and evidence output patterns;
- predeclare generated outputs and their asset mappings;
- keep shared setup in an earlier foundation task;
- create a joint audit for sibling composition;
- use batchable refresh policies for broad boundary inspections when risk permits, while retaining `per-change` for evidence that truly must be refreshed after every task.

Do not persist a proposed parallel batch. The graph should encode truthful dependencies and scopes; the runtime derives the currently safe execution shape from them.
