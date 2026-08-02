---
name: upgrade
description: Upgrade an active Pyramid Task V2 or V2.1 project to V3 in place without rebuilding its graph, losing completed work, or interrupting a claimed task. Use when a legacy project lacks .pyramid/project.json or the user asks to make an existing plan compatible with current brownfield assurance.
---

# Upgrade a Pyramid Task Project

Read `../../references/upgrade-contract.md`, `../../references/brownfield-assurance.md`, and `../../references/lifecycle-contract.md` completely before upgrading.

## Workflow

1. Validate the legacy plan and inspect lifecycle, graph version, active claims, verified nodes, and event count. Restore an archived current plan first; do not release a valid active claim merely for upgrade.
2. Preview the migration:

```bash
python3 ../../scripts/pyramid.py upgrade --project <project-root> --actor <actor> --from-version 2.1 --mode auto --preview --json
```

3. Explain what is byte-preserved, what V3 metadata is derived, the selected mode, bridge gaps, active work, pre-upgrade snapshot, and exact upgrade hash. Ask the user to approve this preview when approval has not already been given.
4. Apply only with explicit approval:

```bash
python3 ../../scripts/pyramid.py upgrade --project <project-root> --actor <actor> --from-version 2.1 --mode auto --approved-by <user> --approval-reference <reference> --approved-upgrade-sha256 <preview-hash> --apply --expected-version <graph-version> --json
```

5. Validate again. Confirm the plan, node states, ownership, prior events, and verified work were preserved. Report the snapshot ID and remaining assurance bridge work.

## Boundaries

- Never rebuild the task graph as an upgrade shortcut.
- Never apply a preview the user did not approve or reuse a hash after inputs changed.
- Treat derived impacts and migrated audits as low-confidence bridge evidence.
- Do not promise that installation alone migrates canonical project data; upgrade is explicit and idempotent.
