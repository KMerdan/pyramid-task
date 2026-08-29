# Runtime Architecture

Pyramid separates deterministic state mechanics from agent reasoning. Skills decide how to gather evidence, choose work, and coordinate agents. Python validates contracts, derives state, and commits guarded mutations.

Demonstrable increments follow the same boundary. Creation and replanning reason from the current usable baseline to an ordered ladder of actor-visible outcomes. They encode each rung with existing outcome, audit, and typed-edge primitives. The runtime enforces those graph relations and audit transitions but does not add mutable increment state or reinterpret `wave` as delivery progress.

Plan refinement follows the same boundary. The `simplify` skill fact-checks and challenges a complete candidate, while `plan-review.schema.json` validates only the shape of its reasoning record. The review and its schema do not prove semantic claims, and candidate refinement does not mutate canonical state; changes to an existing graph still use replan preview and guarded application.

Intra-task helper delegation follows that boundary too. Skills decide when spare host capacity justifies a research or validation helper. `helper-job.schema.json` and `helper-result.schema.json` validate compact envelopes, but no runtime file stores helper lifecycle and no helper owns a graph mutation.

## Current module boundaries

```mermaid
flowchart LR
    H["Codex or Claude Code"] --> K["Skills and references"]
    K --> CLI["pyramid.py CLI adapter"]
    CLI --> CORE["pyramid_core.py transaction facade"]
    CORE --> GRAPH["pyramid_graph.py pure graph rules"]
    CORE --> PAR["pyramid_parallel.py pure batch analysis"]
    PAR --> GRAPH
    CORE --> ASSURE["pyramid_assurance.py assurance rules"]
    CORE --> STORE["Canonical JSON and hash-linked events"]
    CORE --> VIEW["Compiled projections"]
    VIEW --> LIVE["pyramid_live.py"]
    VIEW --> VIS["pyramid_visualizer.py"]
```

The dependency direction is intentional:

- pure domain modules do not import `pyramid_core`;
- `pyramid_core` remains the compatibility facade for existing imports and owns locks, guarded transactions, events, and publication;
- the CLI translates arguments and errors but does not contain domain policy;
- live and static visualization consume validated projections, never partial canonical writes;
- skills may coordinate sub-agents, while the runtime only returns deterministic scheduling facts.

The visualization runtime derives a disposable `observer` read model from the same validated graph projection. It summarizes intent, outcome gates, proof counts, active work, interventions, recommended action, and the selected-path hierarchy without adding mutable dashboard state. The browser renders those semantics as its default landing view and keeps raw graph topology as a technical drill-down.

## Planning and delivery boundary

Planning has four separate dimensions:

| Dimension | Meaning | Canonical representation |
| --- | --- | --- |
| Level | Distance from the final intent | `node.level` |
| Wave | Earliest safe execution time | `node.wave` |
| Parallel batch | Current conflict-safe concurrency | Derived read-only projection |
| Demonstrable increment | Accepted actor-visible project state | Outcome plus `validated-by` audit gate |

The increment ladder is recorded in a selected-path decision and normally forms a cumulative outcome chain: each earlier increment contributes to the next and the final increment contributes to the intent. Each later gate depends on the previous verified increment outcome and repeats or otherwise establishes earlier observable scenarios against the current candidate. A separate final gate is needed only for additional direct intent branches or distinct release-level composition evidence. This structure keeps the plan backward-compatible while ensuring a delivery cycle ends at evidence, not at an arbitrary scheduler boundary.

`pyramid_parallel.py` is read-only. Its output is a disposable projection validated by `parallel-frontier.schema.json`; it is never written into canonical plan or state. A `PARALLEL-W…` ID deterministically correlates one derived plan/wave/task grouping, but it is not canonical identity, history, or a concurrency guard.

## Why not split everything at once

`pyramid_core.py` accumulated storage, validation, projection, query, and lifecycle responsibilities. A big-bang rewrite would create high regression risk in graph history, locks, migration, and serialized contracts. New behavior should land behind pure functions first, then existing functions can move without changing their public signatures.

## Incremental extraction sequence

1. **Graph primitives** — node lookup, typed edges, blockers, and availability. Extracted to `pyramid_graph.py`.
2. **Derived scheduling** — conflict and parallel-frontier analysis. Isolated in `pyramid_parallel.py`.
3. **Storage and publication** — paths, JSON loading, locks, atomic commits, head validation, and event writes.
4. **Projection** — graph, ready index, Markdown, archive, and browser payload compilation.
5. **Task lifecycle** — take, update, pause, resume, audit, and scoped guards.
6. **Topology lifecycle** — create, replan, expand, upgrade, reset, restore, and new-intent transitions.
7. **Queries** — inspect, diff, readiness, and closure views.

Each extraction should preserve the compatibility imports from `pyramid_core.py`, add focused tests around the moved boundary, and avoid serialized changes unless a published schema is updated.

## Parallel orchestration boundary

The runtime answers “which current tasks are safe together?” using only current canonical and assurance state. It does not spawn agents or manage worktrees. One coordinator keeps the only mutable `.pyramid` root; executors work in isolated code worktrees and return patches for verified, sequential integration. The orchestration skill:

1. validates the project;
2. requests a derived group for the available slots;
3. claims tasks centrally and assigns exact packets to isolated executors;
4. verifies and integrates scoped patches before canonical task updates;
5. stops cleanly on unexpected overlap or drift;
6. refreshes shared inspections at the effective boundary required by audit freshness;
7. independently audits tasks and rejoins through the saved common gate;
8. recomputes the next frontier.

This keeps host-specific concurrency outside canonical state while retaining deterministic, testable safety decisions.

## Intra-task helper boundary

Task-level and intra-task parallelism are deliberately separate:

| Layer | Derived by | Unit | State |
| --- | --- | --- | --- |
| Graph-task batch | Deterministic runtime | Independently auditable task | Disposable `parallel-frontier` projection |
| Intra-task helper | Host coordinator reasoning | Read-only question against one snapshot | Ephemeral job/result envelope |

The coordinator reserves graph workers first, then assigns remaining slots to helpers. Preflight helpers read an immutable base and rejoin before relevant design decisions. Candidate helpers run review or validation against an isolated frozen candidate. A result from any other snapshot is stale and cannot become final evidence. Helpers never edit source, mutate `.pyramid`, spawn untracked agents, or publish/deploy.
