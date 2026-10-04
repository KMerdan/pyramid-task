# TASK-411 — directional claims and producer proof

Status: implementation checks passed; canonical task acceptance is recorded separately.
Target: Standalone Pyramid Skill source, local-canonical, `main` based on
`3d787c5c2038d61f1146f24ba20188bfd18b6495`. Both installed plugins remain 4.0.0.
This is not a released or installed 4.1 build.

## Change

New consumers do not change an unchanged provider's claim. A node's own
prerequisites/validation, incoming contributions or invalidation, and alternatives
remain relevant. Composition changes stale the affected parent and ancestors.

New proof-contract identity binds the selected producer's evidence, acceptance,
intent claims, procedure and declared inputs—not every consumer's acceptance.
Each consumer still requires its own implementation and audit.

For existing 4.0 proof, an unchanged current legacy digest remains valid.
When consumer changes alter that digest, guarded replan may record an explicit
version-2 binding for the exact recorded run and identical producer contract.
It first validates the original proof and its current inputs/artifacts. Changed
procedure, selected producer, source, artifacts, failed observations or forged
run identity are not rescued. Historical observations, artifacts and event bytes
are not rewritten. No installation/read-time migration or automatic acceptance
of a new consumer is introduced.

## Actual evidence

- `baseline-failure.txt`: two new regression cases failed against unchanged 4.0
  source; both invalidated the unchanged RESEARCH-101 provider.
- `graph-only-failure.txt`: the directional graph repair passed schema 1 while
  schema 2 still failed at consumer-scoped proof identity.
- `pre-run-capture.json`: captured contract and source fingerprint before the
  final checks. The final submitted proof must use this capture unchanged.
- `consumer-growth-current.json` and `consumer-growth-4.0.json`: real CLI
  subprocess transcripts and an executed probe reading a real producer input.
  Both probes exited 0 with `PASS producer`. The provider stays passed; the new
  consumer stays unverified. Old result/audit/event/artifact bytes remain intact.
  A stale graph guard is refused; changed source makes prior proof unusable.
- `final-tests.txt`: 168 tests passed in 20.728 seconds. Includes positive and
  negative contract, composition, selection, source and identity regressions.
- `repository-validation.txt`: 17 skills and 31 schemas validated.
- `git diff --check` passed on the final candidate.

The 4.0 compatibility scenario executes the candidate runtime with an independently
reproduced frozen 4.0 proof-hash formula. It does not claim an installed 4.0
host was exercised. Schema-1 result/audit fixtures and pure contract tests are
synthetic runtime-contract fixtures, not product execution attestations.
The actual CLI/probe tests do not mock a passing subprocess or its observation.

Reviewer: Codex, actor `codex-pyramid41-worker`; implementation/testing review,
not an independent consequential review. Environment: Python 3.14 in the local
declared development environment, disposable fixtures and owned subprocesses.
One existing HTTP test emitted a Python temporary-directory ResourceWarning;
the suite passed. No rendered UI changed, so visual feedback is not applicable
to this engine slice.

## Attempts and limits

Two intermediate composition-test fixtures were rejected: one duplicated an
existing contribution edge; the other orphaned a node. Both were test-authoring
errors, rejected before mutation. The final valid scenario adds an independent
child. An earlier exploratory 162-test pass was not used as final-candidate
proof. The retained failing-before and graph-only logs remain visible.

Task acceptance, TASK-412, joint GATE-419 and both installed-host qualification
remain separate. The extra targeted-replan/projection-write decision is not
implemented here. Overall assurance can still become stale on replan; this
slice does not silently clear that conservative status.

Evidence is bounded development output, not new authoritative runtime state.
No private session logs, credentials, browser state or production records are
included. No commit, push, installation change or deployment was performed.

