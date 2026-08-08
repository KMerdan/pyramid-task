---
name: visualize
description: Render an existing Pyramid Task V3 project as a self-contained snapshot or live-updating browser graph. Use when a human wants a focused execution view, star chart, pyramid, dependency view, execution frontier, paused handoffs, brownfield assurance overlays, affected assets, inspections, findings, drift, blockers, or clickable node details.
---

# Visualize a Pyramid Task Plan

Read `../../references/visualization-contract.md`, `../../references/handoff-contract.md`, `../../references/brownfield-assurance.md`, and `../../references/lifecycle-contract.md` completely before rendering.

## Workflow

1. Validate the project and surface errors before rendering.
2. Generate a self-contained snapshot by default:

```bash
python3 ../../scripts/pyramid.py visualize --project <project-root> --json
```

Use `--output <path>` only when the user requests a specific destination.

3. When the user asks for continuous updates, start the blocking live server:

```bash
python3 ../../scripts/pyramid.py visualize --project <project-root> --live --json
```

Add `--open` only when the user asks to open it. Keep the process running until the user is finished; live mode prints its loopback URL before serving.

4. Return the absolute generated path for a snapshot or the loopback URL for live mode.
5. Explain only the statuses, blockers, or paths the user asked about. The view itself supplies node detail.

## View semantics

- Treat color, shape, text, and detail labels as complementary signals.
- Keep working, paused, verification, health, and path selection as separate dimensions.
- Show plan lifecycle and `needs-rework` independently from ordinary ready work.
- Use assurance status, impact, inspection, and finding overlays to explain affected scope; never merge task readiness with assurance readiness.
- Calculate layout from graph semantics; do not write presentation coordinates into the canonical plan.
- Use Focus view for immediate work context; retain star, pyramid, and dependency views for structural exploration.
- Keep visualization read-only. Route state changes through `take`, `pause`, `resume`, `update`, `audit`, `expand`, or `replan`.

## Boundaries

- Never derive status separately in the browser.
- In live mode, refresh only after a complete validated `.pyramid/graph.json` publication and retain the last valid graph after a rejected publication.
- Never edit generated HTML as the source of plan truth.
- Never imply that a visual connection is verified when its evidence or gate is pending.
