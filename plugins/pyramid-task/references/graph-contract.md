# Graph Contract

The canonical task source is `.pyramid/plan.json`. Runtime state, lifecycle, reports, archives, and immutable events live beside it. V3 project mode is in `project.json`; brownfield baseline and assurance are separate canonical companions so old plan graphs remain compatible. `.pyramid/head.json` atomically publishes the hashes and composite identity of one committed canonical context. Markdown task files, ready indexes, browser views, and `.pyramid/graph.json` are generated projections.

The composite context is `(plan_id, plan_revision, graph_version, context_id)`. `graph_version` orders mutations within one plan generation; `context_id` binds the complete plan and state so equal numeric versions from resets or restores cannot be confused. Modern events record that identity and the previous event hash. Task and audit packets additionally carry scoped mutation guards. Use those for task-local work so an unrelated evidence refresh does not create a false conflict; use composite context for topology, lifecycle, and full assurance mutations. Use the runtime `diff` query for bounded change summaries instead of placing the full event history in agent context.

Use `schema_version: 1`. Use stable IDs such as `INTENT-001`, `OUTCOME-010`, `CAP-020`, `TASK-101`, `RESEARCH-110`, `CONTRACT-120`, and `GATE-190`.

## Required plan fields

- `schema_version`: integer `1`;
- `plan_id`, `title`, `revision`;
- `intent`: `id`, `statement`, `success_evidence`, `constraints`, `non_goals`, `assumptions`;
- `evidence`: evidence ledger entries;
- `decisions`: selected-path records;
- `nodes`: graph nodes;
- `edges`: typed graph relations.

## Node contract

Every node has:

- `id`, `kind`, `title`, `summary`;
- non-negative `level` and `wave`;
- `workstream`;
- `selection`: `primary`, `alternative`, `rejected`, or `superseded`;
- `source_requirements`;
- `acceptance_criteria` with stable IDs;
- `required_evidence` with stable IDs and types;
- `agent` containing `required_context`, `allowed_write_scope`, `commands`, `deliverables`, and `non_goals`, plus optional work effect, evidence outputs, and generated output patterns with asset IDs.

Kinds are `intent`, `outcome`, `capability`, `work-package`, `decision`, `research`, `contract`, `implementation`, `integration`, `risk-control`, and `audit`.

Executable kinds are `research`, `contract`, `implementation`, `integration`, `risk-control`, and `audit`. Give every executable node a concrete deliverable and acceptance criterion.

A `work-package` is a stable non-executable task contract created by approved expansion. It has at least two primary work branches and a primary audit gate that covers every branch.

## Edge contract

Each edge has `from`, `to`, and `type`.

- `contributes-to`: the source helps establish the target parent;
- `requires`: the source cannot start until the target is verified;
- `contract-requires`: the source cannot start until the target contract is verified;
- `integration-requires`: the source may start, but cannot pass audit until the target is verified;
- `validation-requires`: the source cannot pass audit until the target is verified;
- `validated-by`: the source parent cannot pass until the target audit gate passes;
- `alternative-to`: the source is an alternate route to the target;
- `invalidates`: evidence from the source invalidates the target path.

For dependency edges, `from` is the dependent and `to` is the prerequisite. For `contributes-to`, `from` is the child and `to` is the parent.

## Structural invariants

- Exactly one node matches `intent.id`, has kind `intent`, and has level 0.
- Every primary non-intent node reaches the intent through `contributes-to` edges.
- A `contributes-to` child has a greater level than its parent.
- Hard and contract dependency subgraphs are acyclic.
- All referenced node and evidence IDs exist.
- Every critical intent success item is referenced by at least one node's `source_requirements`.
- Any primary intent, outcome, capability, or work-package with two or more primary contributing children has a `validated-by` audit node whose dependency closure covers every non-gate branch.
- Rejected, alternative, and superseded nodes never become ready.

## State semantics

Execution is `planned`, `working`, `paused`, `implemented`, `needs-rework`, or `superseded`. Verification is `unverified`, `pending`, `passed`, or `failed`. Health is `clear`, `at-risk`, or `blocked`. Availability is derived as `not-executable`, `not-selected`, `locked`, `ready`, `needs-rework`, `working`, `paused`, `implemented`, or `verified`.

Do not place execution state in `plan.json` or hand-edit canonical companions. Use runtime transitions so the commit head, event chain, history, and composite concurrency checks remain intact.

Plan lifecycle is `active`, `completed`, or `archived`. It does not replace node state. Read `lifecycle-contract.md` before closing, reopening, archiving, resetting, cleaning, or restoring a plan.

Read `expansion-contract.md` before converting an executable node into a work-package.

Read `brownfield-assurance.md` before creating or auditing changes in an existing system. Read `upgrade-contract.md` before adding V3 companions to a legacy plan.

Read `handoff-contract.md` before pausing, transferring, or resuming claimed work.
