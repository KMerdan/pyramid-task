# New Intent Transition Contract

`new-intent` is the single lifecycle front door for starting a distinct intent. It prevents agents from treating installation version, project format, and plan lifecycle as the same state.

## Version authority

- The installed plugin manifest and runtime report the executable version.
- `.pyramid/project.json` declares V3 project format.
- `.pyramid/plan.json` and `.pyramid/state.json` are stable compatible contracts and are not V2 markers.
- Existing plans require a valid V3 `project.json`. A missing manifest is unsupported legacy data or a damaged V3 project, not permission to reconstruct it. Restore a damaged V3 manifest from its original backup; do not fabricate one. The runtime no longer migrates V2/V2.1.

## Routing

| Current state | Previewed transition |
| --- | --- |
| No plan | `create` |
| Active V3 plan or active claims | Block and preserve current work |
| Verified but not formally closed plan | Report `close-then-preview-new-intent` so the final report and dossier are produced first |
| Completed V3 plan | `archive → reset` |
| Archived V3 plan | `reset` using the existing archive |
| Legacy plan in any lifecycle state | Reject unsupported format before writes |

## Preview and approval

Preview validates the candidate plan and hashes the exact candidate file, current plan and state, actor, reason, selected mode, transition, blockers and binding warnings. A completed chronicle with pending or unavailable exact code binding remains transitionable, but the warning cannot disappear from the approved material unnoticed. Existing projects require approving user identity, a durable reference, the exact `new_intent_sha256`, and an expected graph version when available. Fresh creation does not require transition approval.

Apply recomputes the preview and rejects stale or changed material. Reset creates or verifies the restorable archive, carries the brownfield baseline and project-wide intent chronicles when present, starts a new assurance bundle and graph version, records the parent transition approval in the new `plan.created` event, and captures the new intent's source starting point. A historical `plan_id` cannot be reused; restore that archive instead.

Only V3 current plans and archive sources are supported. Legacy migration code, `new-intent --from-version`, component migration hashes and upgrade-result fields are removed. Existing V3 migration provenance remains evidence and is not rewritten.

## Discovery conflict

`doctor` reports an old standalone `~/.codex/skills/pyramid-task-planner/SKILL.md` when it still contains the direct `docs/tasks/` workflow. Replace it with `compat/pyramid-task-planner` or remove it from skill discovery. The compatibility skill delegates to V3 and never writes canonical or generated files itself.
