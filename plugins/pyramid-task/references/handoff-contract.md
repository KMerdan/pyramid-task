# Pause, Handoff, and Resume Contract

Pyramid Task treats an interruption as a first-class task transition. It is neither an implementation result nor a plan lifecycle change.

## Scope and state

- Pause and resume are task-level transitions. They never block independent ready nodes.
- Only a `working` executable node owned by the requesting actor can be paused.
- `paused` is an execution state. A paused node is not ready and cannot be claimed by `take`.
- A pause creates `task.paused`; a resume creates `task.resumed`. Events and handoff records preserve the chain.
- `paused` nodes count as active claims so `close`, `archive`, and intent transitions cannot silently discard continuation state.

## Modes and ownership

| Mode | Owner while paused | Resume rule |
| --- | --- | --- |
| `hold` | Original actor through `resume_deadline` | That actor resumes normally. A different actor may resume only after expiry with `--takeover`. |
| `handoff` | No owner | Any actor can resume the canonical record. |

Use `hold` for a coffee break or short context break. Use `handoff` for a conscious transfer. Neither mode implies implementation, verification, audit success, or release.

## Canonical records

The agent writes a `pyramid-handoff-draft-v1` narrative. The runtime validates it and writes immutable records under `.pyramid/handoffs/`:

- `HANDOFF-<task>-<timestamp>-<token>.json` is canonical and conforms to `schemas/handoff.schema.json`.
- The matching Markdown file is a human-readable projection.
- The `task.paused` event binds the canonical JSON content hash; validation rejects later edits or missing records.
- State contains only the active handoff pointer and pause provenance. Resume follows that pointer; it never guesses from an earlier conversation.

The narrative must include progress, changed files/assets, checks, decisions, assumptions, blockers, risks, next steps, a recommended first action, required context, external sessions, and running resources. Empty arrays are meaningful and preferable to invented entries.

## Staleness guard

At pause, the runtime stores the graph version plus hashes for `plan.json`, baseline, assurance, and the non-`.pyramid` Git worktree. Resume compares current values. A difference returns `stale-handoff` without mutation, unless an authorized actor explicitly supplies `--accept-stale` after reviewing the drift.

This guard prevents a resumed agent from assuming that its old scope, affected assets, inspections, or source tree still hold. It does not replace inspection-aware audits or scope-drift handling.

## Lifecycle and recovery

- Do not use archive/reset/release as a break mechanism.
- Archive and reset reject paused tasks because their handoff state is active work.
- Archive snapshots carry historical handoff records; reset purges the current records only after snapshotting them.
- Restore clears active ownership/pause pointers rather than reanimating a historical lease. The handoff records remain recoverable evidence.
