# Lifecycle Contract

The plan lifecycle is independent from each node's execution, verification, health, and availability. Runtime state in `.pyramid/state.json` is authoritative; generated Markdown and HTML are projections.

## Plan states

- `active`: work, audit, approved expansion, and replan mutations are allowed.
- `completed`: the intent and every primary claim are verified, all health is clear, no claim is active, and a final report exists. Ordinary mutations are frozen; reopening verified executable work reactivates the plan.
- `archived`: canonical plan, state, events, evidence, and reports are frozen in a restorable archive. Inspect and visualize the archive directly, or restore it before mutation.

## Repair lifecycle

An executable audit failure changes execution to `needs-rework`, verification to `failed`, and health to `at-risk`. `take` may claim `needs-rework` nodes and prioritizes them in the ready frontier. Implementation moves the node back to `implemented` with verification `pending`; only a passing audit restores `passed`.

Manual `reopen` applies the same repair state to a primary executable node. It invalidates stale dependent proof through hierarchy, dependency, integration, validation, and joint-gate relations. Downstream implementation is preserved, but its verification becomes pending or unverified and health becomes at-risk until the affected path is audited again.

Use local repair when the claim and graph contract remain valid. Use approved `expand` when the contract remains valid but the work needs a deeper internal subtree. Use `replan` when evidence invalidates topology, a contract, an assumption, or the selected path.

## Completion lifecycle

The final intent audit establishes that the intended state is verified. `close` formalizes completion and is allowed only when:

- the intent verification is `passed`;
- every primary node verification is `passed`;
- every primary node health is `clear`;
- no active ownership or lease remains.

Closure writes immutable, versioned `pyramid-final-report-v1` JSON and Markdown reports under `.pyramid/reports/`, records `plan.completed`, and changes the lifecycle to `completed`. Reports contain the intent, success-evidence coverage, verified primary nodes and their audits, decisions, evidence, and residual risks.

## Archive lifecycle

Archive refuses active claims. It records `plan.archived`, changes the current lifecycle to `archived`, compiles a final snapshot, and copies canonical state plus projections into:

```text
.pyramid/archives/<archive-id>/
├── manifest.json
├── .pyramid/
│   ├── plan.json
│   ├── state.json
│   ├── events/
│   ├── reports/
│   ├── graph.json
│   └── ready.json
└── docs/tasks/
```

The manifest records plan and graph identity, previous lifecycle state, archive reason, actor, timestamps, and plan/state hashes. An archived root remains readable by `inspect`, `lifecycle`, and `visualize`.

## Reset and restore

`reset` validates the candidate before mutation, requires a new `plan_id`, refuses active claims, creates or verifies an archive snapshot, then starts the candidate at graph version 1. The new `plan.created` event points to the previous archive. It never mixes event histories between plans.

`restore` resolves an archive ID or archived plan ID, validates the snapshot, archives the current plan when present, installs the selected plan and its history, clears ownership and leases, records `plan.restored`, and regenerates projections. It restores the lifecycle that existed before archiving: active plans resume active, and completed plans remain completed until reopened.

## Clean

`clean` removes only `.pyramid/graph.json`, `.pyramid/ready.json`, `.pyramid/pyramid.html`, and generated `docs/tasks/`, then recompiles them. It hashes the canonical plan, state, and event files before and after and fails if any changed. It does not run against an archived current plan.

## Events

Lifecycle mutations use immutable events:

- `task.reopened`;
- `task.expanded` with proposal hash and approval provenance;
- `plan.completed`;
- `plan.archived`;
- `plan.restored`;
- `plan.created` with reset provenance.

All mutations require an actor. Evidence, reasons, invalidated nodes, report paths, archive IDs, and reset/restore provenance live in event payloads.
