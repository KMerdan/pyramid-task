# Agent and Audit Contracts

The runtime produces compact packets so a worker does not need the entire graph. Agents must keep normal authorization boundaries; plan metadata does not authorize files, services, deployments, messages, or destructive actions.

## Agent task packet

`take` returns `agent-task-v1` for one claimed node with:

- task, graph version, and composite context identity;
- title, purpose, kind, level, wave, and workstream;
- execution, verification, health, blocker, and derived availability;
- goal trace to the intent plus direct parents and children;
- typed dependencies and their state;
- required context and allowed write scope;
- commands, deliverables, and non-goals;
- acceptance criteria and required evidence;
- audit gates and lease expiry.
- brownfield impact IDs, affected asset IDs, inspections, findings, and canonical assurance blockers when applicable.

Start from compact `inspect --ready`, `--blocked`, `--paused`, or `--pending-audits` output. Load a full node packet only for the selected work. Use `diff` for bounded history summaries and request `--detail` only when before/after values are necessary.

Treat a packet as stale after a graph-version or context conflict. Every mutation should pass both `--expected-version` and `--expected-context` from the packet or preview. Refresh instead of guessing how the plan changed.

## Agent result

Submit `agent-result-v1` as JSON:

```json
{
  "schema": "agent-result-v1",
  "task": "TASK-101",
  "outcome": "implemented",
  "changed_files": ["src/example.py"],
  "changed_assets": ["ASSET-EXAMPLE"],
  "checks": [{"command": "python3 -m unittest", "result": "passed"}],
  "acceptance_evidence": [{"criterion": "AC-101-01", "result": "passed", "reference": "tests/test_example.py"}],
  "discovered_risks": [],
  "suggested_graph_changes": []
}
```

Use `blocked` when the task cannot continue inside its existing contract. Report every changed file and known asset. The runtime compares actual scope with predicted impact and opens drift when they differ. Use `suggested_graph_changes` for evidence that may require expansion or replanning; do not mutate topology through a result.

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

Every mutation supplies an actor, expected graph version and context ID when available, reason or result, timestamp, and unique event ID. Events are immutable and hash-linked after this contract is introduced. Generated graph and Markdown files are projections, not mutation interfaces.

When an older standalone `pyramid-task-planner` is also discoverable, the V3 plugin remains authoritative for `.pyramid` and `docs/tasks/`. `doctor` reports the conflict; the compatibility shim delegates rather than writing files.
