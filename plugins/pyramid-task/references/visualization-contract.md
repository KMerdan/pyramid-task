# Visualization Contract

Render the visualization projection derived from `.pyramid/graph.json`, which combines the canonical plan with validated runtime state. Exclude agent-only context, evidence payloads, and full assurance records from the browser payload. Never parse generated Markdown to rediscover topology or calculate status independently.

## Required views

- Focus: place the selected or recommended node at the center and show only its goal trace, prerequisites, children, blockers, and audit gates.
- Star: place the intent at the center and deeper levels on semantic rings.
- Pyramid: place level 0 at the apex and increasing levels below it.
- Dependencies: arrange by execution wave and workstream.

## Required interactions

- Select a node and show its title, purpose, kind, path selection, execution, verification, health, availability, and active or latest handoff identity.
- Highlight its goal trace, prerequisites, children, and audit gate.
- Filter all, ready, working, paused, needs-rework, blocked, audit, work-package, and verified nodes.
- Provide keyboard-accessible view and filter controls plus a node-selection fallback.
- Link to the generated Markdown source when the environment supports local links.
- Overlay assurance status, impact membership, inspections, and findings from the canonical assurance bundle.

## Visual encoding

- Encode execution with node fill.
- Encode paused work with a distinct amber fill and paired handoff text.
- Encode verification with a ring or mark.
- Encode health with a warning mark and text.
- Encode selection with opacity and a label.
- Pair every color signal with text, shape, or line treatment.
- Encode brownfield assurance with a distinct dashed ring and detailed text; never reuse task execution color as assurance state.
- Keep inactive structure neutral and visually subordinate.

The browser is read-only. Actions that claim, pause, resume, update, audit, expand, or replan must call their authoritative interface rather than modifying local presentation state.

## Live runtime

- Treat `.pyramid/head.json` as the canonical commit boundary and the final atomic replacement of `.pyramid/graph.json` as its presentation boundary. Do not broadcast raw `plan.json`, `state.json`, event, or assurance writes.
- Validate the canonical head and require the published graph's composite context to match canonical runtime state before notifying browsers. If the head advances while projection compilation is stalled, retain the last graph and report publication health.
- Use a loopback-only server and reject non-local HTTP Host headers. Expose the current graph through a no-store JSON endpoint and notify clients through a reconnecting event stream.
- After an atomic publication, detect a change within the configured polling interval (250 milliseconds by default). Notify the browser of graph data only when the slim visualization payload changes semantically; generated timestamps and agent-only fields must not cause a rerender. Actual paint time also includes the local request and render round trip.
- Preserve view, filter, overlay, selection, and zoom-compatible browser state across ordinary updates. If a selected node disappears after expansion, replan, reset, or restore, select the recommended current node.
- Retain the last valid graph when publication validation fails and show the failure as connection health, not as task health.
- Coalesce rapid publications when necessary, but never replace a newer graph with an older graph version.
- Keep self-contained snapshot rendering available for archives, sharing, and environments where a local server cannot run.

## Progress

Show project mode, plan lifecycle, verified nodes, ready frontier, rework, active and paused work, blockers, pending audits, baseline revision, impacted versus sufficiently inspected assets, open scope drift, and material findings. Do not invent a completion percentage unless the plan explicitly contains reviewed weights. A labeled coverage count is acceptable.

## Layout

Calculate coordinates at render time from level, wave, workstream, and edges. Grow star rings and pyramid width with graph depth and density instead of collapsing deep levels onto one radius. Do not store browser coordinates in `plan.json`. Support narrow screens, dark and light themes, reduced motion, readable human titles with task IDs as secondary labels, and selection without relying on hover.
