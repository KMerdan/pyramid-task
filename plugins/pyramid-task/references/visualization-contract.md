# Visualization Contract

Render the visualization projection derived from `.pyramid/graph.json`, which combines the canonical plan with validated runtime state. Exclude agent-only context, evidence payloads, and full assurance records from the browser payload. Never parse generated Markdown to rediscover topology or calculate status independently.

## Required views

- **Intent Observer (default):** give a human an at-a-glance narrative from intent to accepted outcomes, current work, interventions, next action, and task hierarchy. Do not require graph literacy.
- **Technical graph:** retain Focus, Star, Pyramid, and Dependencies as drill-down layouts. Focus places the selected or recommended node at the center; Star places intent at the center; Pyramid places level 0 at the apex; Dependencies arranges by wave and workstream.

The Observer and Technical graph are two presentations of one deterministic runtime projection. The Observer is not a second state model and the browser must not infer canonical status.

## Observer questions

The first screen must answer these questions in order:

1. What is the intent and what would prove success?
2. What actor-visible outcome was last verified?
3. What outcome and gate must be proved next?
4. What work is actually active, who owns it, and which outcome does it support?
5. What failed, blocked, drifted, became stale, or paused; why does it matter; and what intervention is indicated?
6. What is the next executable action?
7. How is the selected-path work organized beneath the intent?

Use plain human titles and causal summaries. A count is secondary context, not the story. Keep task IDs, raw enum values, graph version, plan revision, edge types, and record IDs in a technical disclosure or graph detail.

## Required interactions

- Select a node and show its title, purpose, kind, path selection, execution, verification, health, availability, and active or latest handoff identity.
- Highlight its goal trace, prerequisites, children, and audit gate.
- When the selected node is a planned demonstrable increment, focus its outcome and `validated-by` gate and show actual verification and blockers; never infer an increment from wave membership.
- From Observer cards, select work without leaving the semantic context. State why the selected work matters and which outcome it supports before showing machine fields.
- Show the selected-path hierarchy with intent and outcome titles. Suppress rejected or alternative branches by default; keep them in technical exploration.
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

Use visual hierarchy from general to specific: intent and proof, delivery path, current action and intervention, selected detail, then technical topology. Do not place a large node-link graph above the answers a human came to obtain. Pair every issue with its recorded reason and an indicated next response; do not make a viewer decode color or search the graph for causality.

## Proof and test observation

- Treat the outcome audit as the acceptance boundary. Passing task checks may support it but must not make an outcome appear verified.
- For the selected work or outcome, show its acceptance criteria, required evidence, latest implementation-check counts, acceptance-check counts, audit-check counts, proof freshness, and failed or not-run evidence when available.
- Organize evidence by the behavior or claim it proves. Test-layer balance may be a secondary diagnostic; unit, integration, and UI totals are not the primary progress story.
- Show a runnable or demonstrable claim only when the plan defines that outcome and its gate has passed. If the plan lacks an explicit outcome ladder, say so instead of deriving increments from waves.
- Do not reconstruct a red-green-refactor timeline unless canonical events actually record those transitions. Never infer test-driven activity from file names or a final green suite.

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

Live mode is near-real-time publication following, not a transactional subscription to every canonical write. A successful mutation compiles and atomically publishes the projection; the watcher then observes that publication. This boundary prevents the UI from briefly showing mixed plan, state, or assurance data.

## Progress

Lead with verified outcomes, not task completion. Show project mode, plan lifecycle, last accepted outcome, next gate, active work, interventions, recommended action, rework, pending audits, and assurance conditions. Distinguish ahead-of-gate work from accepted progress. Do not invent increment state or a completion percentage unless the plan explicitly contains reviewed weights. A labeled count such as `2 of 4 outcomes verified` is acceptable; raw primary-node coverage is secondary.

## Layout

Calculate coordinates at render time from level, wave, workstream, and edges. Grow star rings and pyramid width with graph depth and density instead of collapsing deep levels onto one radius. Do not store browser coordinates in `plan.json`. Support narrow screens, dark and light themes, reduced motion, readable human titles with task IDs as secondary labels, and selection without relying on hover.
