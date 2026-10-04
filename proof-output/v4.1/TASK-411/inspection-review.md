# TASK-411 scoped post-submission inspection

Performed 2026-10-04T06:43:42Z, after implementation event
`EVENT-20261004T064304076361Z-401035E0` (graph version 6).
Actor: `codex-pyramid41-audit`, the same Codex session as the implementer.
This is not independent consequential review.

Reviewed the source diff and actual regression results retained in README.
Checked the canonical task's harness after submission:
inputs remain `2f2d969df137328bfc577850e4ec1963d53e3172614ff9e6c4cf745eb363cab7`;
run `RUN-95F0B160A25EC5CC503D624CD9108F5D` is reusable, setup blockers empty.
Every staged observation artifact's SHA-256 matches. No source edit occurred
between final checks and this inspection; reuse is valid. No second execution
is asserted merely to satisfy a timestamp.

- IMPACT-GRAPH / INSPECT-GRAPH: directional claim relations preserve unchanged
  providers, while changed prerequisites and parent composition invalidate the
  affected claim/ancestors. Actual disposable CLI transitions and schema-1 API
  contract regressions cover these boundaries.
- IMPACT-PROOF / INSPECT-PROOF: producer-scoped identity separates shared
  observations from consumer acceptance. Guarded compatibility binds an exact
  valid stored 4.0 run to identical producer inputs; history remains untouched.
  Negative tests reject changed source/procedure/selection, malformed metadata,
  absent required binding and altered observations with the old run identity.
- IMPACT-REGRESSION-I1 / INSPECT-REGRESSION-I1: 168 tests and 31 schemas passed
  on the captured candidate. New CLI tests execute their probe and mutations;
  synthetic schema-1/contract fixtures are explicitly labeled, not asserted as
  product probes.

Reviewed all six declared implementation files plus bounded task evidence;
canonical submission reports no drift. No UI changes require visual capture.
Only these three impacts/inspections are updated. Thirteen other inspections,
future impact hypotheses, controls and all joint/host gates remain pending.
A later overlapping implementation must refresh the affected proof/inspection
before its consuming audit. No overall 4.1 or installed-host acceptance is given.

