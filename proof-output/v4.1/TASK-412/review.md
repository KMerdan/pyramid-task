# TASK-412 source/authority review

Candidate captured before review: 774d744f3eefddc52e0032b69acd706b4dab21d02f45e8a63b768eeb98d9abfb.
Reviewed current mutation guards/check_expected_guard, task claim/resume paths
and helper contract; repository validator passed (17 skills/31 schemas), diff check passed.

The maintained recipe now separates reviewed source from current invocation
authority and passes the guard through arguments/scoped invocation data. A fresh
lease requires no executable-source edit. A stale guard requires relevant-state
reconciliation, not blind retry. Source fingerprints and actual environment/artifact
freshness still decide whether proof may be reused.

Host authorization remains external to Pyramid; denied operations stay denied.
Helper envelopes retain their current-job/snapshot/guard checks. A renewed guard
alone does not promote an older helper or its observation. Source/authority
dynamic join is a distinct GATE-419 obligation, not a static-review pass.

Reviewer: Codex, same implementation session. This is static contract inspection,
not actual host permission attestation, independent joint review or browser proof.
One multi-file patch attempt had a stale context line and was rejected; the next
narrow patch corrected it. No failed execution was converted to successful proof.
Both installed plugins unchanged. No UI or runtime state-machine change in this task.

