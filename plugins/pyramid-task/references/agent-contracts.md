# Agent and Audit Contracts

The runtime produces compact packets so a worker does not need the entire graph. Agents must keep normal authorization boundaries; plan metadata does not authorize files, services, deployments, messages, or destructive actions.

Authorization, review, readiness, implementation and verification are distinct.
For instruction authoring or ambiguous terminology, consult `operational-language.md`;
normal task work does not require loading that profile.

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
| Explain a prior intent or code path | `history --intent <id>` or `history --path <path>` |
| Build bounded reproduction context | `history --replay <id>` |
| Diagnose interrupted intent history | `history --doctor` |
| Reconcile assurance records | `inspect --assurance-detail` |

Current-plan mutation history is stored as one hash-linked file per mutation under `.pyramid/events/`; it is not appended to the task packet or stored as a version array in the current graph JSON. Cross-intent causal history is stored separately under `.pyramid/history/` and queried through `history`. Do not read either record directory directly for normal work.

CLI output is compact by default: duplicate event before/after snapshots become an explicit event reference; payloads, warnings and invalidations remain. For `update` only, the unchanged task contract (including static harness contracts) is omitted and the packet is labeled `agent-status-v1`. Harness capture/guide pointers, dependencies, health, ownership and guards remain. Take/resume still return complete task contracts. If another mutation intervened before response assembly, update conservatively returns the full packet. `omitted_fields` discloses the projection; canonical records and Python API output are unchanged. Use `--full` when a decision needs the original complete command response; explicit `--compact` remains supported. Read only the selected node or referenced event to recover missing detail, never repeat a mutation. Compact status is not proof-readiness: use `inspect --audit-readiness` before audit.

For additive implementation-file/context discoveries inside an unchanged working task, read `task-amendments.md`. `amend` constructs the candidate internally, preserves ownership, emits a new guard, and records the reviewed delta. It does not approve semantic scope expansion or pass an audit.

If projection metadata would make a response larger, the default returns it unchanged. Consumers must read `schema`/`response_format`, not assume every response contains an `agent-status-v1` packet or event reference. `--full` disables the output projection but does not expand the selected query: use `diff --detail` or `inspect --assurance-detail` for those additional scopes.

## Stable procedure, fresh invocation authority

Keep two identities separate: the reviewed procedure/source fingerprint and the
current task/audit mutation guard. A lease refresh or unrelated graph event is
not a source edit. Pass the guard as invocation data, not a literal embedded in
the reviewed script, generated executable or proof input.

1. Freeze the procedure and its behavior-affecting inputs before review/checks.
2. Obtain the relevant guard from the current packet or audit-readiness query.
   Check the exact project, node, actor and requested operation before invoking it.
3. Pass that guard through an argument or scoped environment variable. The
   existing runtime validates it when the operation runs; reading a guard is not
   a lease renewal, implementation claim or approval.
4. If the runtime rejects authority as stale, inspect only the affected packet.
   Reconcile the changed contract/state. Use a fresh guard only if the intended
   operation is still valid. Do not edit procedure source merely to renew authority.
5. Reuse proof only when its contract, source, environment and artifacts remain
   current. Changed procedure inputs require fresh proof even with a fresh guard.

For example, a reviewed caller may receive `--expected-guard` from its invocation
arguments. Do not put the current `GUARD-TASK-...` into that caller's source.
Do not print credentials or persist broad host state to obtain invocation data.

A Pyramid guard does not grant host permissions, deployment authority or approval
for another project. A denied host operation remains denied. A fresh guard does
not make an older helper result current: apply `intra-task-helpers.md`'s identity,
snapshot, current-guard and evidence reconciliation before using its result.

## Ephemeral intra-task helpers

A task owner may use spare host slots for bounded read-only research or snapshot-isolated validation. Validate prompts and responses with `helper-job.schema.json` and `helper-result.schema.json`, and follow `intra-task-helpers.md` for eligibility, freshness, slot accounting, and reconciliation.

Helper envelopes are not canonical Pyramid state and never enter normal task packets or event history. They echo the parent task guard for freshness correlation, but the coordinator keeps mutation authority and owns every mutation. Raw results start pending and ineligible. A coordinator may promote candidate validation evidence only after the job identity, task guard, immutable snapshot, budgets, and evidence references match the accepted candidate. Copy only reconciled evidence into the parent `agent-result-v1`.

## Agent result

For schema-2 plans, the packet additionally carries a scoped `harness` contract. Read `development-harness.md` for `inspect --harness <id>`, pre-run capture, actual visual review, proof artifacts and run reuse. Add `proofs` to the result below; the old reference-only example is insufficient by itself. Check/acceptance summaries may be omitted or empty when proofs supply them. Raw logs and images are not injected into task packets.

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

Schema-2 passing audits require candidate-bound proofs (explicit runs/reuse, or revalidation of the target's last implementation proof). They also check prerequisite proof freshness. Failed audits retain ordinary failed checks so missing or broken proof cannot prevent recording failure. The Observer shows recorded verification; current working-tree eligibility comes from audit readiness, not historical green state.

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
- Unsupported legacy projects are rejected before mutation; existing V3 migration provenance and assurance obligations remain intact.
- New-intent preview separates installed runtime, project format, and lifecycle state, then binds an archive/reset or reset sequence to one user-approved hash.

A completed plan rejects take, pause, resume, update, audit, expand, and replan. An archived plan rejects every canonical mutation. Use the lifecycle interface for close, archive, reset, restore, clean, and manual reopen semantics.

Every mutation supplies an actor, an appropriate scoped or global guard, reason or result, timestamp, and unique event ID. Global graph versions continue to order immutable hash-linked events; they are not used as a false dependency between unrelated worker and inspection mutations. Generated graph and Markdown files are projections, not mutation interfaces.

When an older standalone `pyramid-task-planner` is also discoverable, the V3 plugin remains authoritative for `.pyramid` and `docs/tasks/`. `doctor` reports the conflict; the compatibility shim delegates rather than writing files.
