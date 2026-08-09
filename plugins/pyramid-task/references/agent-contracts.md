# Agent and Audit Contracts

The runtime produces compact packets so a worker does not need the entire graph. Agents must keep normal authorization boundaries; plan metadata does not authorize files, services, deployments, messages, or destructive actions.

## Agent task packet

`take` returns `agent-task-v1` for one claimed node with:

- task, graph version, composite context identity, and task/audit mutation guards;
- title, purpose, kind, level, wave, and workstream;
- execution, verification, health, blocker, and derived availability;
- goal trace to the intent plus direct parents and children;
- typed dependencies and their state;
- required context and allowed write scope;
- commands, deliverables, and non-goals;
- acceptance criteria and required evidence;
- audit gates and lease expiry;
- brownfield impact IDs, affected asset IDs, inspections, findings, and canonical assurance blockers when applicable.

Start from compact `inspect --ready`, `--blocked`, `--paused`, or `--pending-audits` output. Load a full node packet only for the selected work. Use `diff` for bounded history summaries and request `--detail` only when before/after values are necessary.

Use `mutation_guards.task` for take, update, and pause, and `mutation_guards.audit` for audit. These guards bind only the task contract, relevant state, baseline, impact map, implementation frontier, and applicable assurance. An unrelated inspection refresh may advance global history without invalidating a worker guard. Continue using graph version plus context ID for topology, lifecycle, full assurance, reset, and restore mutations. Refresh the smallest relevant packet after a scoped conflict.

| Need | Smallest context source |
| --- | --- |
| Choose work | `inspect --ready` |
| Continue one task | `inspect --node <id>` or the packet returned by `take`/`update` |
| Decide whether an audit can run | `inspect --audit-readiness <id>` |
| Explain recent history | `diff --from-version <n>` |
| Inspect one history payload | `diff --from-version <n> --detail` |
| Reconcile assurance records | `inspect --assurance-detail` |

Canonical history is stored as one hash-linked file per mutation under `.pyramid/events/`; it is not appended to the task packet or stored as a version array in the current graph JSON. Do not read the event directory directly for normal work.

## Agent result

Submit `agent-result-v1` as JSON:

```json
{
  "schema": "agent-result-v1",
  "task": "TASK-101",
  "outcome": "implemented",
  "changed_files": ["src/example.py"],
  "changed_assets": ["ASSET-EXAMPLE"],
  "change_effect": "mixed",
  "changes": [{"path": "src/example.py", "class": "source"}],
  "checks": [{"command": "python3 -m unittest", "result": "passed"}],
  "acceptance_evidence": [{"criterion": "AC-101-01", "result": "passed", "reference": "tests/test_example.py"}],
  "discovered_risks": [],
  "suggested_graph_changes": []
}
```

Use `blocked` when the task cannot continue inside its existing contract. Report every changed file and known asset. Classify files as `source`, `generated`, `runtime`, `configuration`, `evidence`, or `unknown` when the distinction affects invalidation. Evidence-only output must stay inside declared evidence scope. Generated output requires a plan-time glob and asset mapping: this prevents false drift but still invalidates behavior inspections covering the generated asset. The runtime compares actual scope with predicted impact and opens drift when they differ. Use `suggested_graph_changes` for evidence that may require expansion or replanning; do not mutate topology through a result.

`agent.effect` declares whether a task is expected to produce source changes, evidence only, or a mixture. It is a validation boundary, not an instruction to hide incidental product changes. Generated-output asset IDs must exist in the current baseline, and evidence-only results may not classify product files as evidence.

## Audit result

Submit `audit-result-v1` as JSON:

```json
{
  "schema": "audit-result-v1",
  "target": "GATE-190",
  "result": "pass",
  "checks": [{"id": "CHECK-190-01", "result": "passed", "evidence": ["test-output.txt"]}],
  "affected_claims": ["OUTCOME-010"],
  "recommended_action": "advance",
  "assurance": {
    "impact_ids": ["IMPACT-001"],
    "inspection_ids": ["INSPECTION-001"],
    "finding_ids": [],
    "scope_review": "complete",
    "limitations": []
  }
}
```

A passing audit requires a non-empty check list and no failed check. In brownfield mode it also requires an assurance assertion after enforcement begins. The runtime resolves asserted IDs against canonical impact, inspection, and finding records, rejects missing or invented coverage, and enforces scope drift, material finding, control, and legacy-bridge blockers. A failure records the failed check, affected claims, and a repair, impact reconciliation, expansion, or replan recommendation.

## Ownership and transitions

- `take` changes a ready executable node to working and assigns an expiring lease.
- Only the owner may update or release an active claim.
- `pause` changes an owned working node to paused, stores an immutable handoff, and either retains the owner through a hold deadline or releases ownership for transfer.
- `resume` follows the active handoff pointer, detects stale graph/assurance/worktree context, acquires a fresh lease, and returns the task to working with an enriched continuation packet.
- Paused nodes remain active work and cannot be claimed through `take`, closed, archived, reset, or silently replaced.
- `implemented` clears ownership and sets verification pending.
- `audit pass` sets verification passed only after structural prerequisites are satisfied.
- `audit fail` sets an executable node to needs-rework, verification failed, and health at-risk, then invalidates stale dependent proofs.
- `reopen` applies the same repair state to a primary executable claim and reactivates a completed plan when needed.
- Replanning preserves unchanged node state, initializes new nodes, and marks removed nodes superseded.
- Approved expansion preserves the task ID and contract, converts it to a work-package, initializes child branches and a joint gate, and invalidates stale dependent proofs.
- Baseline change, replan, expansion, reopen, audit failure, or undeclared scope stales affected inspections and assurance.
- Brownfield close writes a change dossier and advances the baseline revision.
- In-place upgrade preserves legacy node state and active ownership while introducing conservative future assurance enforcement.
- New-intent preview separates installed runtime, project format, and lifecycle state, then binds any upgrade/archive/reset sequence to one user-approved hash.

A completed plan rejects take, pause, resume, update, audit, expand, and replan. An archived plan rejects every canonical mutation. Use the lifecycle interface for close, archive, reset, restore, clean, and manual reopen semantics.

Every mutation supplies an actor, an appropriate scoped or global guard, reason or result, timestamp, and unique event ID. Global graph versions continue to order immutable hash-linked events; they are not used as a false dependency between unrelated worker and inspection mutations. Generated graph and Markdown files are projections, not mutation interfaces.

When an older standalone `pyramid-task-planner` is also discoverable, the V3 plugin remains authoritative for `.pyramid` and `docs/tasks/`. `doctor` reports the conflict; the compatibility shim delegates rather than writing files.
