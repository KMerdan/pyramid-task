# Intra-Task Helper Contract

Pyramid may use spare host-agent capacity for bounded research, reconnaissance, review, or validation inside one claimed task. These helpers are ephemeral execution aids. They are not graph nodes, parallel-frontier groups, canonical scheduler records, events, owners, mutation guards, or independent completion claims.

The coordinator owns the parent task, the global agent-slot ledger, every canonical `.pyramid` mutation, and all decisions based on helper output.

## Eligibility

Create a helper only when:

- its question is independent of the coordinator's current work;
- its expected value is greater than its coordination cost;
- a host slot remains after reserving the coordinator and all selected graph-task workers;
- its source access can remain read-only;
- repository-bound work can read an immutable snapshot; and
- the coordinator knows when the result must rejoin.

Good preflight jobs include repository mapping, dependency or API research, test discovery, acceptance-to-evidence mapping, and risk review. Good candidate jobs include independent review, static analysis, and test execution against a frozen candidate.

Do not delegate trivial reads, canonical Pyramid queries or mutations, topology decisions, approval-requiring actions, secret handling, publishing, deployment, or any source edit. A check is not inherently read-only: tests and builds may create caches, coverage, generated output, databases, snapshots, or lockfile changes. Run such commands only in a disposable worktree or sandbox that cannot modify the coordinator's worktree.

## Phases and freshness

`preflight` helpers inspect a stable base snapshot. Their output is advisory and must rejoin before any load-bearing decision it can affect. The coordinator may continue only work that is independent of the open question.

`candidate` helpers inspect a frozen candidate snapshot. Use an immutable Git commit, content hash, or external source-set identifier. If any relevant file changes afterward, the result is stale. Candidate-bound evidence becomes final only when the coordinator confirms that the returned snapshot exactly matches the candidate accepted for the parent task.

Never point a helper at a live tree while another agent is editing it. If the host cannot provide a stable snapshot or isolated command execution, keep repository-bound validation serial.

## Job envelope

Validate jobs against `helper-job.schema.json`. Send only the parent task ID, helper purpose, exact snapshot, narrow read scope, linked acceptance criteria, explicit questions, prohibitions, join boundary, and bounded result budget.

```json
{
  "schema": "helper-job-v1",
  "helper_id": "HELPER-TASK-203-RESEARCH-01",
  "parent_task": "TASK-203",
  "task_guard": "GUARD-TASK-0123456789ABCDEF0123456789ABCDEF",
  "kind": "research",
  "phase": "preflight",
  "snapshot": {
    "kind": "git-commit",
    "id": "0123456789abcdef0123456789abcdef01234567",
    "immutable": true
  },
  "read_scope": ["src/router/**", "tests/router/**"],
  "purpose": "Identify the existing routing invariants before implementation.",
  "questions": ["Which tests define fallback and retry behavior?"],
  "acceptance_criteria": ["AC-203-01"],
  "execution_isolation": "none",
  "prohibited_actions": [
    "write-canonical-worktree",
    "mutate-pyramid",
    "spawn-agents",
    "publish-or-deploy",
    "change-git-history"
  ],
  "join_before": "load-bearing-decision",
  "result_budget": {
    "max_findings": 8,
    "max_evidence_items": 12,
    "max_output_chars": 8000
  }
}
```

## Result envelope and reconciliation

Validate returned data against `helper-result.schema.json`. A helper reports claims and evidence; it does not approve the parent task or promote its own output to final evidence.

```json
{
  "schema": "helper-result-v1",
  "helper_id": "HELPER-TASK-203-RESEARCH-01",
  "parent_task": "TASK-203",
  "task_guard": "GUARD-TASK-0123456789ABCDEF0123456789ABCDEF",
  "kind": "research",
  "phase": "preflight",
  "snapshot": {
    "kind": "git-commit",
    "id": "0123456789abcdef0123456789abcdef01234567",
    "immutable": true
  },
  "status": "completed",
  "summary": "Fallback behavior is covered by the router contract tests.",
  "findings": [
    {
      "claim": "Fallback retries once before returning the terminal error.",
      "confidence": "high",
      "evidence": ["tests/router/test_fallback.py"],
      "recommendation": "Preserve the retry boundary."
    }
  ],
  "evidence": ["tests/router/test_fallback.py"],
  "checks": [],
  "stale_if": ["The router implementation or fallback tests change."],
  "evidence_use": "advisory",
  "freshness": "pending",
  "final_evidence_eligible": false,
  "eligibility_reason": "Preflight evidence is advisory.",
  "changed_files": [],
  "changed_assets": [],
  "risks": []
}
```

The task guard in a helper envelope is correlation and freshness context, not mutation authority. Helpers never invoke Pyramid mutations with it.

Keep that correlation data outside reviewed executable source. Follow
`agent-contracts.md`'s stable-procedure/fresh-invocation recipe. Renewing parent
authority does not automatically requalify a helper, change its immutable
snapshot, or grant denied host permissions; reconcile against the current job.

The coordinator rejects or treats as stale any result whose helper ID, parent task, task guard, phase, or snapshot differs from the job. It also compares the returned guard to the current parent-task guard and enforces the job's finding and evidence budgets. `changed_files` and `changed_assets` must be empty. Reconcile contradictions explicitly and copy only accepted, relevant evidence into the parent `agent-result-v1`.

Raw helpers return `freshness: pending` and `final_evidence_eligible: false`. During reconciliation, the coordinator may mark a completed candidate validation `current` and eligible only after its job identity, task guard, snapshot, budgets, and evidence references match. If the current guard or accepted candidate differs, mark the result stale. Preflight evidence and any result from an older snapshot remain advisory.

## Slot ownership

Graph-task workers have priority because they advance independently auditable outcomes. Calculate helper capacity globally:

```text
helper_slots = host_agent_capacity - coordinator - active_graph_task_workers
```

Do not count a helper slot twice or allow untracked nested delegation. A worker may request a helper, but only the coordinator may reserve the slot and issue the job. Stop spawning when the host limit, task-worker reservation, or returned result budget would be exceeded.
