---
name: lifecycle
description: Manage the full lifecycle of a Pyramid Task V3 plan. Use when Codex must reopen failed or stale work, reactivate a completed intent, close a fully assured graph with a change dossier, freeze it, safely reset while carrying the baseline, clean projections, inspect archives, or restore a plan without losing history.
---

# Manage a Pyramid Task Lifecycle

Read `../../references/lifecycle-contract.md`, `../../references/graph-contract.md`, `../../references/agent-contracts.md`, and `../../references/brownfield-assurance.md` completely before changing lifecycle state.

## Start with status

```bash
python3 ../../scripts/pyramid.py lifecycle --project <project-root> --json
```

Use its lifecycle status, closure blockers, active claims, graph version, and archive IDs. Never infer closure merely from an empty ready frontier.

## Repair work

An audit failure automatically moves an executable node to `needs-rework` and invalidates dependent proofs. Reopen a passed or completed claim when newer evidence makes it stale:

```bash
python3 ../../scripts/pyramid.py reopen --project <project-root> --node TASK-203 --actor <actor> --reason <reason> --evidence <evidence.json> --json
```

Omit `--evidence` only when no structured file exists. Reopening a completed plan reactivates it. Use `take`, `update`, and `audit` to repair and reverify the invalidated path; use `replan` when the topology or selected mechanism is wrong.

## Complete and freeze

Close only after the intent audit passes and `closure_ready` is true:

```bash
python3 ../../scripts/pyramid.py close --project <project-root> --actor <actor> --json
```

Closing writes a versioned JSON and Markdown final report and blocks ordinary execution mutations. In brownfield mode it also writes a change dossier and advances the baseline revision. Archive a completed or intentionally paused plan after releasing every active claim:

```bash
python3 ../../scripts/pyramid.py archive --project <project-root> --actor <actor> --reason <reason> --json
```

## Reset, clean, and restore

Reset requires a fully validated candidate plan with a new `plan_id`. It archives the current plan before replacement; brownfield mode carries the current baseline and prior dossiers into a fresh assurance cycle:

```bash
python3 ../../scripts/pyramid.py reset --project <project-root> --plan <new-plan.json> --actor <actor> --reason <reason> --json
```

Clean only generated graph, ready, Markdown, and browser artifacts, then regenerate them. It preserves plan, state, reports, and events byte-for-byte:

```bash
python3 ../../scripts/pyramid.py clean --project <project-root> --json
```

Restore by archive ID or archived plan ID. The runtime first archives any current plan:

```bash
python3 ../../scripts/pyramid.py restore --project <project-root> --archive <archive-or-plan-id> --actor <actor> --reason <reason> --json
```

## Boundaries

- Never use `create --force`, delete `.pyramid`, or hand-edit lifecycle state to restart.
- Never archive, reset, or restore over active claims; release them first.
- Treat final reports and archive manifests as evidence artifacts, not mutable working notes.
- Preserve the original success criterion after failure. Repair locally or replan from evidence.
- Use `--expected-version` on mutations when coordinating concurrent agents.
