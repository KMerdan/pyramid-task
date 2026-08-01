# Agent and Audit Contracts

The runtime produces compact packets so a worker does not need the entire graph. Agents must keep normal authorization boundaries; plan metadata does not authorize files, services, deployments, messages, or destructive actions.

## Agent task packet

`take` returns `agent-task-v1` with:

- task and graph version;
- title, purpose, kind, level, wave, and workstream;
- execution, verification, health, blocker, and derived availability;
- goal trace to the intent plus direct parents and children;
- typed dependencies and their state;
- required context and allowed write scope;
- commands, deliverables, and non-goals;
- acceptance criteria and required evidence;
- audit gates and lease expiry.

Treat a packet as stale after a graph-version conflict. Refresh instead of guessing how the plan changed.

## Agent result

Submit `agent-result-v1` as JSON:

```json
{
  "schema": "agent-result-v1",
  "task": "TASK-101",
  "outcome": "implemented",
  "changed_files": ["src/example.py"],
  "checks": [{"command": "python3 -m unittest", "result": "passed"}],
  "acceptance_evidence": [{"criterion": "AC-101-01", "result": "passed", "reference": "tests/test_example.py"}],
  "discovered_risks": [],
  "suggested_graph_changes": []
}
```

Use `blocked` when the task cannot continue inside its existing contract. Use `suggested_graph_changes` for evidence that may require expansion or replanning; do not mutate topology through a result.

## Audit result

Submit `audit-result-v1` as JSON:

```json
{
  "schema": "audit-result-v1",
  "target": "GATE-190",
  "result": "pass",
  "checks": [{"id": "CHECK-190-01", "result": "passed", "evidence": ["test-output.txt"]}],
  "affected_claims": ["OUTCOME-010"],
  "recommended_action": "advance"
}
```

A passing audit requires a non-empty check list and no failed check. A failure records the failed check, affected claims, and a repair, expansion, or replan recommendation.

## Ownership and transitions

- `take` changes a ready executable node to working and assigns an expiring lease.
- Only the owner may update or release an active claim.
- `implemented` clears ownership and sets verification pending.
- `audit pass` sets verification passed only after structural prerequisites are satisfied.
- `audit fail` sets an executable node to needs-rework, verification failed, and health at-risk, then invalidates stale dependent proofs.
- `reopen` applies the same repair state to a primary executable claim and reactivates a completed plan when needed.
- Replanning preserves unchanged node state, initializes new nodes, and marks removed nodes superseded.
- Approved expansion preserves the task ID and contract, converts it to a work-package, initializes child branches and a joint gate, and invalidates stale dependent proofs.

A completed plan rejects take, update, audit, expand, and replan. An archived plan rejects every canonical mutation. Use the lifecycle interface for close, archive, reset, restore, clean, and manual reopen semantics.

Every mutation supplies an actor, expected graph version when available, reason or result, timestamp, and unique event ID. Events are immutable. Generated graph and Markdown files are projections, not mutation interfaces.
