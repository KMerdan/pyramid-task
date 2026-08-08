# Lifecycle Contract

The plan lifecycle is independent from each node's execution, verification, health, and availability. Runtime state in `.pyramid/state.json` is authoritative; generated Markdown and HTML are projections.

## Plan states

- `active`: work, audit, approved expansion, and replan mutations are allowed.
- `completed`: the intent and every primary claim are verified, all health is clear, no claim is active, and a final report exists. Ordinary mutations are frozen; reopening verified executable work reactivates the plan.
- `archived`: canonical plan, state, events, evidence, and reports are frozen in a restorable archive. Inspect and visualize the archive directly, or restore it before mutation.

## Repair lifecycle

An executable audit failure changes execution to `needs-rework`, verification to `failed`, and health to `at-risk`. `take` may claim `needs-rework` nodes and prioritizes them in the ready frontier. Implementation moves the node back to `implemented` with verification `pending`; only a passing audit restores `passed`.

Manual `reopen` applies the same repair state to a primary executable node. It invalidates stale dependent proof through hierarchy, dependency, integration, validation, and joint-gate relations. Downstream implementation is preserved, but its verification becomes pending or unverified and health becomes at-risk until the affected path is audited again. Brownfield reopening also stales affected inspections and assurance; reopening a completed plan keeps the prior report and dossier as historical artifacts but clears them as the current completion references.

Use local repair when the claim and graph contract remain valid. Use approved `expand` when the contract remains valid but the work needs a deeper internal subtree. Use `replan` when evidence invalidates topology, a contract, an assumption, or the selected path.

## Session continuity

A temporary interruption uses task-level `pause`, not plan archive or claim release. A paused task retains a canonical handoff pointer and counts as active work, while independent tasks remain available. `resume` validates that handoff against current graph, assurance, and worktree state before returning the node to `working`. See `handoff-contract.md` for ownership modes, required evidence, stale-handoff handling, and takeover rules.

## Completion lifecycle

The final intent audit establishes that the intended state is verified. `close` formalizes completion and is allowed only when:

- the intent verification is `passed`;
- every primary node verification is `passed`;
- every primary node health is `clear`;
- no active ownership or lease remains.
- for brownfield mode, the baseline and assurance have no final blockers: impact and inspections are sufficient, drift and material findings are dispositioned, controls are ready or justified, and any legacy bridge is sufficient.

Closure writes immutable, versioned `pyramid-final-report-v1` JSON and Markdown reports under `.pyramid/reports/`, records `plan.completed`, and changes lifecycle to `completed`. Brownfield closure also writes `pyramid-change-dossier-v1` JSON and Markdown under `.pyramid/dossiers/`, advances the baseline revision, and marks assurance passed. The dossier reconciles predicted impact with actual changes and records inspections, findings, audits, controls, residual risk, and the baseline transition.

## Archive lifecycle

Archive refuses active claims. It records `plan.archived`, changes the current lifecycle to `archived`, compiles a final snapshot, and copies canonical state plus projections into:

```text
.pyramid/archives/<archive-id>/
├── manifest.json
├── .pyramid/
│   ├── plan.json
│   ├── state.json
│   ├── project.json
│   ├── baseline.json
│   ├── assurance.json
│   ├── events/
│   ├── handoffs/
│   ├── reports/
│   ├── dossiers/
│   ├── graph.json
│   └── ready.json
└── docs/tasks/
```

The manifest records plan and graph identity, previous lifecycle state, archive reason, actor, timestamps, and plan/state hashes. An archived root remains readable by `inspect`, `lifecycle`, and `visualize`.

## Reset and restore

`reset` validates the candidate before mutation, requires a new `plan_id`, refuses active claims, creates or verifies an archive snapshot, then starts the candidate at graph version 1. The new `plan.created` event points to the previous archive. It never mixes event histories between plans. Brownfield reset carries the current baseline and prior dossiers, but starts a fresh assurance bundle for the new intent.

For a distinct intent, `new-intent` is the preferred front door. Its preview chooses `create`, `upgrade → archive → reset`, `archive → reset`, or a blocked route from the actual project format and lifecycle. Existing projects require the exact transition hash and approval provenance. The new `plan.created` event records that parent approval. See `new-intent-contract.md`.

`restore` resolves an archive ID or archived plan ID, validates the snapshot, archives the current plan when present, installs the selected plan and its history, clears ownership, leases, and active pause pointers, records `plan.restored`, and regenerates projections. Historical handoff files remain preserved as evidence. It restores the lifecycle that existed before archiving: active plans resume active, and completed plans remain completed until reopened.

## Clean

`clean` removes only `.pyramid/graph.json`, `.pyramid/ready.json`, `.pyramid/pyramid.html`, and generated `docs/tasks/`, then recompiles them. It hashes plan, state, project manifest, baseline, assurance, events, handoffs, reports, and dossiers before and after and fails if canonical data changed. It does not run against an archived current plan.

## Events

Lifecycle mutations use immutable events:

- `task.reopened`;
- `task.paused` with handoff identity, mode, deadline, and content hash;
- `task.resumed` with lease, takeover, and accepted-staleness provenance;
- `task.expanded` with proposal hash and approval provenance;
- `plan.completed`;
- `plan.archived`;
- `plan.restored`;
- `plan.created` with reset provenance.
- `plan.created` with new-intent transition approval when reset was composed by `new-intent`;
- `project.upgraded` with approval hash and snapshot provenance;
- `assurance.baseline-assessed` and `assurance.impact-updated`.

All mutations require an actor. Evidence, reasons, invalidated nodes, report paths, archive IDs, and reset/restore provenance live in event payloads.
