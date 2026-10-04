# Bounded 4.1 host pilot

facts.md and request.md are the shared input. Each host runs baseline 4.0 and
candidate 4.1 serially with the same facts, tool limits and model defaults.
Candidate snapshots and baseline snapshots are frozen in owned temporary
directories. Codex discovers repository-local .agents/skills; Claude loads
the snapshot with session-only --plugin-dir. Installed plugins are unchanged.

The pilot measures decisions from actual native-host tool traces and final
actions, not model self-ratings. Case evidence is sanitized/supplied, not a
live product/VM/DB/browser experiment. Native skill discovery and the disposable
runtime inspection are actual operations. Private logs/auth files are excluded.
The evaluator rubric and all outputs stay outside the host's permitted context.

Use proof-output/v4.1/TASK-422/summary.md for measured results in a development
checkout. Missing counters stay unknown. One matched batch per host cannot
establish general token savings, host reliability or end-to-end productivity.
