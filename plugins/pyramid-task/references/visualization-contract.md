# Visualization Contract

Render `.pyramid/graph.json`, which combines the canonical plan with validated runtime state. Never parse generated Markdown to rediscover topology or calculate status independently.

## Required views

- Star: place the intent at the center and deeper levels on semantic rings.
- Pyramid: place level 0 at the apex and increasing levels below it.
- Dependencies: arrange by execution wave and workstream.

## Required interactions

- Select a node and show its title, purpose, kind, path selection, execution, verification, health, and availability.
- Highlight its goal trace, prerequisites, children, and audit gate.
- Filter all, ready, working, needs-rework, blocked, audit, work-package, and verified nodes.
- Provide keyboard-accessible view and filter controls plus a node-selection fallback.
- Link to the generated Markdown source when the environment supports local links.
- Overlay assurance status, impact membership, inspections, and findings from the canonical assurance bundle.

## Visual encoding

- Encode execution with node fill.
- Encode verification with a ring or mark.
- Encode health with a warning mark and text.
- Encode selection with opacity and a label.
- Pair every color signal with text, shape, or line treatment.
- Encode brownfield assurance with a distinct dashed ring and detailed text; never reuse task execution color as assurance state.
- Keep inactive structure neutral and visually subordinate.

The browser is read-only. Actions that claim, update, audit, expand, or replan must call their authoritative interface rather than modifying local presentation state.

## Progress

Show project mode, plan lifecycle, verified nodes, ready frontier, rework, active work, blockers, pending audits, baseline revision, impacted versus sufficiently inspected assets, open scope drift, and material findings. Do not invent a completion percentage unless the plan explicitly contains reviewed weights. A labeled coverage count is acceptable.

## Layout

Calculate coordinates at render time from level, wave, workstream, and edges. Grow star rings and pyramid width with graph depth and density instead of collapsing deep levels onto one radius. Do not store browser coordinates in `plan.json`. Support narrow screens, dark and light themes, reduced motion, readable labels, and selection without relying on hover.
