# Changelog

All notable changes follow semantic versioning. Serialized task graph and state schemas keep their existing version where backward compatibility is preserved; the project manifest declares the V3 format.

## Unreleased

### Documentation

- Refresh the README screenshot from the current 3.5 interface and make the conceptual parallel lifecycle match the implemented orchestration boundary.
- Specify the deterministic parallel batch-ID algorithm and clarify that batch IDs are disposable correlation handles, not canonical versions, scheduler state, or mutation guards.

## 3.5.0

### Conflict-safe parallel execution

- Add a read-only `inspect --parallel-ready --max-agents` query that derives deterministic same-wave batches from current readiness, dependency, write/evidence/generated scope, asset, inspection-policy, and scope-drift state.
- Publish compact claim guards, isolation guidance, shared evidence refresh boundaries, common join gates, serial reasons, and pairwise conflicts without adding parallel state to the canonical graph.
- Add the `pyramid-task:orchestrate` skill for host-neutral sub-agent coordination with exact worker packets, one canonical coordinator, isolated source worktrees, and targeted rejoin audits.
- Preserve task-guard validity across unrelated parallel claims and validate the new output with a published schema and focused runtime tests.

### Runtime architecture

- Extract pure graph/readiness primitives and parallel analysis from the core transaction facade, with an incremental architecture plan for storage, projection, lifecycle, and query boundaries.
- Document the parallel workflow with a README diagram, planning guidance, context limits, and Codex/Claude Code behavior from one branch.

### Documentation

- Reorganize the README around the current architecture, scoped context model, assurance timing, live publication behavior, and single-branch Codex/Claude installation.
- Document immutable event storage versus compact agent context, the mutation-to-guard routing table, inspection refresh-policy semantics, fanout warnings, and generated-output asset validation.
- Update published examples and contributor invariants to demonstrate the current typed change and inspection contracts.
- Align expansion proposal agent fields with the typed plan contract so tasks can be preserved and expanded without schema rejection.

## 3.4.0

### Conflict-isolated assurance

- Add task- and audit-scoped mutation guards so inspection-only assurance refreshes do not invalidate unrelated worker packets while the global graph version continues to order immutable history.
- Use one implementation-freshness engine for readiness, task packets, visualization, lifecycle closure, and audit; add `inspect --audit-readiness` with exact blockers and the minimal inspection refresh set.
- Bind performed inspections to exact `task.implemented` event frontiers, retain timestamp fallback for existing bundles, and warn about high-fanout inspections and repository-root assets.
- Make impact preview hashes deterministic by excluding publication metadata and derive assurance status under the project lock.
- Add typed source, generated, runtime, configuration, evidence, and unknown changes; evidence-only artifacts avoid product drift and invalidation only within declared output scope.
- Add generated-output patterns with asset mappings, selective inspection invalidation classes, refresh policies, and baseline exclude locators while keeping existing V3 plans and assurance bundles readable.

## 3.3.0

### Exact context at mutation time

- Add a composite context identity that binds plan ID, plan revision, graph version, and complete runtime state; mutation commands can reject both stale versions and wrong plan generations.
- Publish canonical file hashes and the latest event through atomic `.pyramid/head.json`, and hash-link new events while preserving legacy event readability.
- Add compact frontier, blocker, pause, audit, assurance-summary, and bounded event-diff queries; retain full node, assurance, and event detail only on explicit request.
- Serialize projection compilation and cleanup under the project lock so concurrent agents cannot publish mixed generated views.
- Route skill prompts through progressive disclosure and carry the exact context guard from query or task packet into mutations.

### Live, focused visualization

- Add a loopback-only, Host-restricted live visualization server with no-store graph delivery and reconnecting server-sent update events.
- Refresh only after canonical head and graph contexts agree, preserve browser context, and retain the last valid graph when a publication is rejected or delayed.
- Exclude agent-only contracts and full assurance records from browser payloads, and rerender only for semantic visualization changes.
- Add a default Focus view, execution summary, recommended-node navigation, human-readable node labels, and changed-node highlighting.
- Preserve the self-contained static visualization for archives, sharing, and offline inspection.

## 3.2.0

### Durable session continuity

- Add task-level `pause` and `resume` transitions without stopping independent graph work.
- Persist immutable JSON and Markdown handoffs containing progress, changed scope, checks, decisions, blockers, risks, next actions, context, external sessions, and running resources.
- Add `hold` mode for short owner-retained breaks and `handoff` mode for deliberate ownership transfer.
- Detect stale handoffs from graph, plan, baseline, assurance, and source-worktree fingerprints before resuming.
- Add `pyramid-task:pause` and `pyramid-task:resume` agent skills plus published draft and canonical handoff schemas.
- Surface paused tasks and handoff identity in inspect, lifecycle, graph, Markdown, archive/clean preservation, and the interactive browser.

## 3.1.0

### Safe intent transitions

- Add a deterministic `new-intent` preview/apply workflow for fresh projects, completed V3 plans, and completed V2/V2.1 clusters.
- Compose legacy upgrade, validated snapshots, archive, reset, baseline carry-over, and new-plan initialization under one approval-bound transition hash.
- Block active plans, active claims, and ambiguous archived-legacy transitions instead of replacing work by inference.
- Extend `doctor` with runtime version, project format, lifecycle routing, recommended action, and stale standalone planner detection.
- Add a dedicated `pyramid-task:new-intent` skill and a V3 compatibility shim for old `pyramid-task-planner` installations.
- Clarify that `project.json` identifies V3 project format while `plan.json` and `state.json` remain compatible canonical contracts.

## 3.0.0

### Brownfield by default

- Auto-detect non-empty repositories as brownfield projects while retaining explicit greenfield mode.
- Add agent skills for system assessment, change-impact analysis, and in-place legacy upgrade.
- Keep legacy plans readable and add a previewed, hash-bound, user-approved V2/V2.1 migration that preserves the plan, node state, active claims, results, audits, lifecycle, and event history.
- Carry verified baselines and change dossiers across reset, archive, restore, and clean lifecycle operations.

## 2.4.0 — Assurance enforcement

- Require inspection-aware assurance assertions on brownfield audit passes.
- Detect undeclared changed files and assets as scope drift.
- Invalidate inspections after implementation, baseline change, audit failure, reopen, expansion, or replan.
- Block material open findings and require evidenced rollback, monitoring, and legacy-bridge closure.
- Generate a change dossier and advance the baseline when a brownfield intent closes.

## 2.3.0 — Brownfield visibility

- Add `project.json`, `baseline.json`, and `assurance.json` canonical companions while keeping V2 plan and state files compatible.
- Add deterministic `assess`, `impact`, and assurance inspection interfaces.
- Enrich agent packets, Markdown projections, graph snapshots, lifecycle status, and the browser with affected assets and assurance blockers.
- Add browser overlays for assurance status, impact, inspections, findings, and scope drift.

## 2.2.0

- Add user-approved recursive task expansion, stable work-packages, stronger joint-gate coverage, and deep-graph visualization.
