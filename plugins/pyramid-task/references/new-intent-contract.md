# New Intent Transition Contract

`new-intent` is the single lifecycle front door for starting a distinct intent. It prevents agents from treating installation version, project format, and plan lifecycle as the same state.

## Version authority

- The installed plugin manifest and runtime report the executable version.
- `.pyramid/project.json` declares V3 project format.
- `.pyramid/plan.json` and `.pyramid/state.json` are stable compatible contracts and are not V2 markers.
- Absence of `project.json` means the current project data is legacy, even when the installed runtime is V3.

## Routing

| Current state | Previewed transition |
| --- | --- |
| No plan | `create` |
| Active plan or active claims | Block and preserve current work |
| Verified but not formally closed plan | Report `close-then-preview-new-intent` so the final report and dossier are produced first |
| Completed legacy plan | `upgrade → archive → reset` |
| Completed V3 plan | `archive → reset` |
| Archived V3 plan | `reset` using the existing archive |
| Archived legacy plan | Block until restore/upgrade or an explicit baseline decision |

## Preview and approval

Preview validates the candidate plan and hashes the exact candidate file, current plan and state, actor, reason, selected mode, transition, blockers, and component upgrade hash. Existing projects require approving user identity, a durable reference, the exact `new_intent_sha256`, and an expected graph version when available. Fresh creation does not require transition approval.

Apply recomputes the preview and rejects stale or changed material. A legacy completed plan first receives a validated pre-upgrade snapshot and V3 evidence bridge. Reset then creates or verifies the restorable archive, carries the brownfield baseline when present, starts a new assurance bundle and graph version, and records the parent transition approval in the new `plan.created` event.

The composite operation is recoverable rather than destructive: if reset cannot proceed after upgrade, the upgraded current plan and pre-upgrade snapshot remain valid and inspectable.

## Discovery conflict

`doctor` reports an old standalone `~/.codex/skills/pyramid-task-planner/SKILL.md` when it still contains the direct `docs/tasks/` workflow. Replace it with `compat/pyramid-task-planner` or remove it from skill discovery. The compatibility skill delegates to V3 and never writes canonical or generated files itself.
