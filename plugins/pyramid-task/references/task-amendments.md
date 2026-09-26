# Narrow task amendments

Use `amend` for additive implementation-file or read-context discoveries inside an unchanged task outcome. It is not a shortcut for changed intent, acceptance, dependencies, commands, deliverables, proof procedures/inputs, non-goals, generated-output policy, or authority. Those changes still require replan.

## Eligibility

- The actor owns a working primary executable task with an unexpired lease.
- Additions name existing regular repository files, not directories, globs, symlinks, external paths, Git/Pyramid metadata, or generated task projections.
- New write paths do not overlap another working or paused task's write, evidence, or generated-output scope. Unknown active scope is treated conservatively.
- In brownfield mode every new write path resolves only to assets already mapped to this task. Reconcile missing impact through `impact` first.
- In a schema-2 plan every added write path must already be captured by at least one of this task's resolved proof input contracts, including shared proof. Evidence-output exclusions apply exactly as during capture. Missing setup for other inputs does not block amendment, but still blocks proof collection. If coverage is missing, replan the proof contract; do not broaden inputs automatically or recapture old evidence to disguise a change.
- Evidence-only write-policy changes, removals, new files, and semantic contract changes use replan. An already permitted write path needs no amendment.

Review why the additions preserve the task outcome, acceptance, non-goals, dependencies, authority and proof sufficiency. Input coverage is not proof that the procedure tests the newly discovered behavior. Changed assumptions or procedures require replan, even when a glob covers the file. The runtime validates structural restrictions; it cannot prove an agent's semantic assertion. Existing product/security approval boundaries still apply. Do not use repeated amendments to hide an expanding outcome.

## Submit only the delta

Write `pyramid-amendment-v1` (see `../schemas/amendment.schema.json`):

```json
{
  "schema": "pyramid-amendment-v1",
  "task": "TASK-203",
  "reason": "The reproduced leak is owned by this existing connection helper.",
  "boundary_review": "The helper repair preserves the existing acceptance, recovery behavior, dependencies and authority; evidence: reports/leak-reproduction.md.",
  "add_write_paths": ["src/storage/connection.py"],
  "add_context_paths": []
}
```

```bash
python3 ../../scripts/pyramid.py amend --project <project-root> --proposal <amendment.json> --actor <owner> --preview --json
python3 ../../scripts/pyramid.py amend --project <project-root> --proposal <amendment.json> --actor <owner> --apply --expected-amendment <preview-amendment-id> --json
```

Review the preview before applying. Its token binds the actor, exact proposal, canonical plan/state, baseline and assurance. Re-preview if any of them changed. No whole-plan candidate or whole-plan review is required.

Apply assembles and validates the complete candidate internally, advances plan revision and graph version, retains the owner/lease/execution state, and publishes a hash-linked `task.amended` event with the proposal and changed fields. Use the returned fresh `mutation_guard` for subsequent task updates. Apply the returned additions to the packet already in context, or inspect only this node if that packet was lost.

Write-scope amendments conservatively stale affected brownfield inspections using existing invalidation rules; context-only additions do not. No audit is passed, scope drift dismissed, or finding resolved by an amendment. Existing update/audit checks still enforce actual implementation evidence.

An amendment alone does not change a bound proof's source fingerprint or acceptance contract. Subsequent edits to captured inputs invalidate proof normally. Recapture before the next actual check and submit fresh observations. Schema-1 plans remain legacy-unbound; amendment does not silently adopt schema 2.
