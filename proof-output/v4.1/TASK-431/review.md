# TASK-431 bounded footprint proof

Captured inputs before final checks: 158d6feb7888ceb89497c38a23cebe3a0aafccc0c70f28876a3e02ada1aa42bb.
Five actual filesystem/API/CLI tests passed in 0.341 seconds. The public CLI
summary/detail calls compare every regular fixture file's hash and mtime before
and after; no files change. A real failed audit remains failed and its evidence
stays present/currently referenced. Contract classification uses explicit fixture
declarations, not extension-based inference or a mocked filesystem.

The optional query scans metadata only, at most 10,000 entries by default
(explicit maximum 100,000); detail lists at most 100 paths. It reports partial
totals when capped or unreadable, logical bytes rather than disk/Git size, and
does not follow symlinks. Normal queries do not invoke the scan. Git metadata,
.venv, node_modules and Python caches are excluded and reported. Current result/
audit references are visible; archived, historical and active-handoff ownership
is explicitly unknown, never inferred safe to delete.

Real proof-input files overlapping any declared evidence-output glob now refuse
capture instead of disappearing from the source fingerprint. Dedicated staging
must remain outside behavior-input patterns. Unknown purpose remains unknown.
No scan deletes, labels evidence irrelevant, archives, expires or rewrites files.

Retained failing-before: old CLI rejected --footprint; missing API was an import
error; the overlap-negative assertion failed. Final tests now exercise those paths.
Reviewer: Codex same-session engineering/test review. No screenshot claim or UI
change. This is not installed-host qualification or automatic retention cleanup.
