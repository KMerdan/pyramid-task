# 4.1 local candidate qualification

Date: 2026-10-04. Target: Standalone Pyramid Skill source repository, local-canonical,
main. No Hemkar Service, Hemkar Skill or Hemkar CLI operation.

## Candidate identity

Base Git HEAD and observed origin/main:
3d787c5c2038d61f1146f24ba20188bfd18b6495. Source changes are uncommitted.
Both candidate manifests and RUNTIME_VERSION are 4.1.0. The final source and
isolated Codex/Claude package digests agree:
df53c9a28a83a0a73717b821fa1742f1f18793c68f37286e2b94e7337e943440.
See package-identity.json for the exact algorithm and file hashes.
Portable candidate-plan.json is revision 6; canonical revision 7 adds the narrow
TASK-432 documentation scope through guidance-amendment.json. No acceptance,
proof procedure/input, dependency, intent or authority was changed by that amendment.

## Actual checks

- qualified-tests.txt: 176 tests, 20.583 seconds, OK. qualified-test-result.json
  binds the actual command, pre-run fingerprint, digest and artifact hashes. Repository validator:
  17 skills, 31 schemas. Diff whitespace check passes. Existing HTTPError 421
  temporary-object ResourceWarning remains visible, not a test failure.
- TASK-411/final-candidate: real public-CLI producer probes, schema-2 current and
  exact 4.0 legacy formula, consumer addition, source-stale rejection and unchanged
  recorded observations. Schema-1 directionality and negative composition/selection
  cases use controlled state fixtures; they are not real customer acceptance.
- guard-qualified-result.json (with earlier TASK-412/guard-join-final-result.json): actual create/take/pause/resume through CLI,
  changed lease/guard, old invocation rejected, new invocation accepted. Caller
  Earlier caller SHA256 remained 138fa26efcc11d7a5cd8f8db1b12bcd928838d007cb5368da628972de08418c6;
  the reasoned final recipe remained 95510cfbd66bb736f3be835f505e1604af4833dd433099a060adf363ab9c32ee.
  Host authority was unchanged; this owned fixture does not qualify deployment.
- Footprint and overlap regressions use real temporary trees/public CLI and actual
  failed audit refusal. Pure classification fixtures and publication fault injection
  are deliberately synthetic. No deletion, GC or historical-retention confidence.
- recovery-final-result.json: actual 4.0 provider proof, 4.1 guarded binding and
  matching-source/canonical-snapshot restore. Blind 4.0 use of bound live state
  remained unready; restored 4.0 source/snapshot validated and retained later
  history record bytes. Archive/snapshot/per-record hashes and actual stale-audit
  refusal are recorded. The earlier assertion-label failure is preserved separately.
- TASK-422/summary.md and bounded native traces: normal authenticated Codex 0.155.1
  repository-local skill path and Claude 2.1.286 session-only plugin path actually
  loaded and ran the owned ready probe. These do not qualify user installation or
  a real VM/database/browser/mail case. Claude model was claude-opus-5-5; Codex's
  actual model identifier was not exposed.

The native pilot found no critical false-evidence/authority regression. Claude's
4.0 extension premise was wrong; a narrow current harness clarification states
the explicit binding rule. Earlier denied/incomplete attempts are retained.
Final Claude recommends the correct conditional rule but did not inspect runtime
code; source identity/behavior are checked by manifest and separate CLI tests.

Aggregate candidate input accounting increased on both hosts. No token savings,
general speed/reliability gain or end-to-end productivity claim is supported.
Projection tests demonstrate actual byte/mtime behavior only.

## Lifecycle and remaining boundary

Implementation/local qualification evidence is available. The first independent
review exposed record gaps; its report remains preserved. With explicit additional
transfer approval, the focused independent review conditionally accepted the joins.
Its package-identity condition is satisfied by actual hashing of both reviewer
directories; exact source/rejection/restore hashes are in the final recovery trace.
See join-review.md for the complete reconciliation and remaining limits. Canonical
gates must still consume current proof and assurance, not this report alone.

Source package qualification is not publication or user installation. Existing
Codex/Claude 4.0.0 caches, other projects and production were not changed. No commit,
push, deployment, catalog update or blanket artifact cleanup was performed.

Recovery procedure: retain pre-change canonical snapshot plus matching source;
archive the changed active state before restore, retain the newer project-wide
history, restore matching source/snapshot, validate, and recheck proof readiness.
Do not rewrite a run to make old runtime acceptance green.

Ongoing release check: validate repository, run current regression, compare the
exact packaged source hashes and native qualification inputs, query current proof
readiness and bounded footprint. New producer/source/environment changes require
affected fresh proof. This is a bounded local check procedure, not a scheduler,
production monitor or automatic host updater.
