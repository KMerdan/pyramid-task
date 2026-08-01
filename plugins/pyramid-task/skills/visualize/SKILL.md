---
name: visualize
description: Render an existing Pyramid Task V2 project as a self-contained interactive browser graph. Use when a human wants a star chart, pyramid, dependency view, execution frontier, blockers, pending audits, evidence state, or clickable node details from the canonical plan.
---

# Visualize a Pyramid Task Plan

Read `../../references/visualization-contract.md` and `../../references/lifecycle-contract.md` completely before rendering.

## Workflow

1. Validate the project and surface errors before rendering.
2. Generate or refresh the view:

```bash
python3 ../../scripts/pyramid.py visualize --project <project-root> --json
```

Use `--output <path>` only when the user requests a specific destination.

3. Return the absolute generated path. Open it in an available browser only when the user asks to open it.
4. Explain only the statuses, blockers, or paths the user asked about. The view itself supplies node detail.

## View semantics

- Treat color, shape, text, and detail labels as complementary signals.
- Keep working, verification, health, and path selection as separate dimensions.
- Show plan lifecycle and `needs-rework` independently from ordinary ready work.
- Calculate layout from graph semantics; do not write presentation coordinates into the canonical plan.
- Keep visualization read-only. Route state changes through `take`, `update`, `audit`, `expand`, or `replan`.

## Boundaries

- Never derive status separately in the browser.
- Never edit generated HTML as the source of plan truth.
- Never imply that a visual connection is verified when its evidence or gate is pending.
