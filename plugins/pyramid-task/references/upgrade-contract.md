# In-Place Upgrade Contract

Upgrade converts a running legacy Pyramid Task plan to format V3 without rebuilding its graph or discarding work.

## Detection and preview

A project without `.pyramid/project.json` is legacy. Run `upgrade --preview` first. Preview is read-only and deterministically hashes:

- the canonical plan and state;
- source version and selected project mode;
- the generated V3 manifest;
- the conservatively derived baseline and assurance bridge.

The preview reports node, state, verified-node, active-claim, and immutable-event counts plus assurance gaps. Repeating preview against unchanged inputs returns the same approval hash.

## Apply protocol

Apply requires the exact preview hash, approving user, durable approval reference, and expected graph version when available. The runtime rejects changed inputs and stale versions.

Before mutation it writes a validated pre-upgrade archive snapshot. Apply then adds `project.json` and, for brownfield mode, `baseline.json` and `assurance.json`; records one immutable `project.upgraded` event; and regenerates projections.

The plan file is byte-preserved. All node states, results, audits, ownership, leases, lifecycle data, and previous events are preserved. Only the graph version and state update time advance through the upgrade event. A currently working task remains working for the same owner.

## Conservative evidence bridge

Migration derives asset candidates from legacy required context, allowed write scope, and recorded changed files. The derived baseline remains `incomplete`; migration creates low-confidence impact records and marks legacy passing audits as partial inspections. It never upgrades a legacy pass into sufficient brownfield inspection evidence.

Previously verified nodes remain verified; the graph is not replayed. Enforcement begins with the upgraded graph version for future audit passes. An active plan must close its legacy bridge gaps through targeted impact review and sufficient inspections. A previously completed plan records the bridge as documented and remains readable without reopening completed work.

## Idempotency and recovery

Running upgrade on a V3 project returns `up-to-date` and does not create another event. Archived current plans must be restored before upgrade. The pre-upgrade snapshot can be inspected or restored with normal lifecycle commands if recovery is required.

Do not delete V2 state, recreate the graph, synthesize user approval, or claim that derived low-confidence records are verified evidence.

When a completed legacy intent is immediately followed by a distinct new intent, use `new-intent` instead of manually sequencing commands. Its parent approval hash covers the candidate and the upgrade/archive/reset route, while the component upgrade hash remains recorded in the upgrade event.
