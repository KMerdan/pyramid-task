---
name: visualize
description: Render an existing Pyramid Task V3 project as a human-first intent observer or technical graph, in a self-contained snapshot or live-updating browser view. Use when a human wants to understand intent progress, proven outcomes, active work, issues, next action, task structure, demonstrable increments, or detailed graph and brownfield assurance state.
---

# Visualize a Pyramid Task Plan

Render the intent observer first. Read `../../references/visualization-contract.md` only when explaining view semantics, `../../references/demonstrable-increments.md` only when explaining delivery progress, `../../references/handoff-contract.md` only for paused-node details, `../../references/brownfield-assurance.md` only when assurance overlays exist, and `../../references/lifecycle-contract.md` only for lifecycle interpretation.

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
5. Lead the explanation with the intent, last proven outcome, next proof, active work, and interventions. Mention graph mechanics only when the user asks for technical detail.

## View semantics

- Treat color, shape, text, and detail labels as complementary signals.
- Keep working, paused, verification, health, and path selection as separate dimensions.
- Show plan lifecycle and `needs-rework` independently from ordinary ready work.
- Use assurance status, impact, inspection, and finding overlays to explain affected scope; never merge task readiness with assurance readiness.
- Calculate layout from graph semantics; do not write presentation coordinates into the canonical plan.
- Make the Observer the default. It must answer, in plain language: what the intent is, what outcome was last proven, what proof comes next, what is actually working, what needs intervention and why, what action is recommended, and how work contributes to outcomes.
- Show the selected-path task hierarchy and outcome path before raw topology. Keep IDs, graph revisions, enums, edge types, overlays, and mutation mechanics behind technical disclosure or the Technical graph.
- Use Focus view for technical work context; retain star, pyramid, and dependency views for structural exploration and debugging.
- For increment progress, show the outcome, its `validated-by` gate, required proof, actual checks, and blockers. Never relabel a wave, batch, implemented task set, or passing unit suite as a usable increment.
- Present test evidence by the behavior or acceptance claim it supports. Distinguish implementation checks from accepted audit proof and show zero evidence honestly.
- Keep visualization read-only. Route state changes through `take`, `pause`, `resume`, `update`, `audit`, `expand`, or `replan`.

## Boundaries

- Never derive status separately in the browser.
- In live mode, refresh only after a complete validated `.pyramid/graph.json` publication and retain the last valid graph after a rejected publication.
- Never edit generated HTML as the source of plan truth.
- Never imply that a visual connection is verified when its evidence or gate is pending.
