# Changelog

All notable changes follow semantic versioning. Serialized task graph and state schemas keep their existing version where backward compatibility is preserved; the project manifest declares the V3 format.

## 4.2.0 — 2026-10-05 (local source candidate)

- Separate recorded acceptance, current proof eligibility and live publication health; correct completed-intent actions and expose bounded claim-linked evidence.
- Avoid unused graph construction in narrow inspect queries; add selected assurance, invocation-local input hashing and explicit full-response recovery. No persisted validation cache or weaker guards.
- Clarify routine-query, health-update, proof-reuse and final-validation triggers with original STE-inspired guidance; keep authorization, proposed grants, review and verification separate.
- Make the Observer decision-centered, responsive and keyboard-operable, with honest dependency/status labels and lazy claim-linked raster evidence. Bound reads, reject symlink/nonregular/FIFO paths and download non-raster evidence as opaque attachments.
- Add drafting-only `goal-prompt`, adapting to project, phase, harness and confirmed authority. There are 18 skills, still 26 CLI commands and 31 schemas.
- Retain failed working runs locally; publish bounded summaries. Actual browser/model inspection and independent checks are distinct from contract fixtures. No native token/human-comprehension claim, push, installation upgrade, compaction or cleanup.

See the [improvement index](docs/planning/improvement/README.md). This entry does
not assert remote publication or a user's installation status.

## 4.1.0 — 2026-10-04 (source published)

Source qualification completed and was pushed to `main` in `58559af`.
Publication does not update installed plugins or qualify a user's installation;
see [current context](CONTEXT.md) for status and boundaries.

- Make replan invalidation directional: a new consumer preserves an unchanged provider; changed producer claims, inputs and composition still invalidate affected claims.
- Bind schema-2 proof to its producer contract rather than all current consumers. Add explicit guarded compatibility bindings for intact recorded 4.0 runs without rewriting observations, artifacts or history. Older runtimes cannot be assumed to understand new binding metadata; recovery must restore matching source and canonical snapshots, not downgrade a live plan blindly.
- Separate stable reviewed procedure/source identity from fresh task/audit guards passed as invocation data. Preserve host permission and current proof checks.
- Add a small original STE-inspired operational language profile, routed on demand. Distinguish authorization, review and verification; retain blocked evidence while independent authorized work continues. Scope the first increment to a complete public journey and only necessary harness capability.
- Recompute and validate complete projections, but skip byte-identical ready/Markdown writes. Timestamped graph output still changes; no token savings follow from fewer writes.
- Add optional bounded read-only `inspect --footprint` with logical-byte/count summaries, declared classes, current references, partial-scan limits and unknown ownership. No deletion, GC, extension-only classification or normal-packet scan.
- Reject rooted/specific proof-input overlap with evidence outputs and repository-wide output globs during capture; keep dedicated staging exclusions for whole-repository captures and amendment coverage.
- Retain failing attempts and qualify source/runtime and native host paths separately. See the 4.1 planning/evidence index for actual checks and matched pilot limitations; qualification does not establish production or installed-plugin acceptance, or measured token savings.

## 4.0.0

- Route natural-language “usage audit” and workflow-overhead questions through `inspect`, distinct from task evidence `audit`, with coverage-aware, read-only analysis guidance and README examples.
- Breaking: remove the V2/V2.1-to-V3 `upgrade` skill, CLI/API, migration helpers, preview schema and reference. Remove `new-intent --from-version`, internal migration and migration-only response fields. The catalog now has 17 skills and 26 CLI commands.
- Reject unsupported legacy current plans and archive sources before writes, including direct reset/restore paths. Preserve ordinary V3 safeguards, schema-1 V3 plans, historical migration provenance and existing assurance obligations. Test real CLI rejection, byte-preservation and V3 continuation.
- Add local cross-project CLI usage counters and read-only `inspect --usage`, including zero-count commands, outcomes, unfinished calls, runtime and stdout bytes. Support UTC day windows and mode/version/format detail without adding a skill or top-level command.
- Keep counters separate from canonical project evidence and plugin caches; store no raw arguments or project identities, support opt-out, and fail open on storage restrictions. Document that CLI calls do not measure skill invocation or model tokens.
- Test actual multi-project and concurrent CLI processes, read-only reports, opt-out, interrupted execution and locked/corrupt storage. Isolate all tests from real user counters.

## 3.9.0

- Integrate the guarded task-amendment and compact-output work from `1eea7dd`. Existing-file additions within an unchanged owned task use a preview-bound delta instead of a full plan rewrite; ownership, conflict checks, assurance invalidation and causal history remain intact.
- Make amendments harness-aware: schema-2 write additions must already belong to the task's resolved proof inputs using the same glob and evidence-output exclusions as capture. Changed proof requirements still require replan; covered source edits invalidate old proof normally.
- Make compact CLI projections the default, with explicit omissions and event references; add `--full` for decisions needing the original command response and retain explicit `--compact`. Preserve full canonical/Python API data, failed evidence, warnings, blockers and fresh guards; keep take/resume packets complete and fall back to a full update packet if another mutation intervened. CLI consumers requiring the old complete response shape must use `--full`.
- Route create/replan references by the current decision, reuse current baseline/packet context, and avoid whole-plan review for eligible amendments. Preserve candidate refinement and outcome-scoped harness obligations.
- Add amendment/harness integration and output-safety regression tests. Output bytes and reference word counts are context-size proxies, not measured end-to-end model token or latency savings.
- Add an executed subprocess failure/repair/audit test through the CLI and document the limits of synthetic proof and visual fixtures. Clarify that health/release updates need no new test run and that CLI compact output does not trigger host conversation compaction.

## 3.8.1

- Enforce portable recursive-glob syntax before matching proof inputs: `**` must occupy a complete path component. Reject malformed patterns consistently on Python 3.10, 3.12 and 3.13, including patterns that would otherwise match files on newer Python.
- Reject those patterns during plan validation as well as candidate capture; retain the same schema and lifecycle contracts.

## 3.8.0

### Outcome-scoped development harness

- Plan the smallest sufficient external, internal and applicable visual observations alongside each outcome; reuse existing project tools and implement only missing probe/capture capability before acceptance.
- Add plan schema 2 with criterion-linked proof contracts and shared proof references. Keep project format V3 and state schema 1; preserve legacy schema-1 execution and require explicit guarded replan for adoption. Reject downgrades and prevent older runtimes from silently ignoring bound-proof requirements.
- Add read-only `inspect --harness` with task-scoped instructions, pre-run candidate fingerprints, setup blockers and reusable runs. Generate `docs/tasks/DEVELOPMENT_HARNESS.md` from canonical contracts rather than maintaining a second acceptance guide.
- Validate declared source/fixture/environment inputs, required observations and hashed artifacts at update/audit; recheck prerequisite proof at audit and all primary proof at closure. Preserve failed checks instead of replacing them with passing summaries.
- Deduplicate bounded proof artifacts in existing report storage and retain them through archive/reset/restore. Keep model visual review and external runtime identity explicit agent responsibilities.
- Integrate harness guidance with planning, implementation, helpers, replan/expand, pause/resume, assurance and lifecycle without adding a scheduler, universal test runner, node kind or mutable harness ledger.

### Correctness and recovery

- Reject malformed, empty-evidence and duplicate audit checks. Invalidate changed proof families and old/new dependent claims on replan while retaining implementation history and unrelated verified work.
- Preserve explicit `resume --for-recovery` for blocked paused tasks and keep blocked handoffs discoverable without bypassing ownership, dependency, stale-context or takeover checks.
- Normalize historical check status/result synonyms conservatively and avoid recording symbolic refs as commit identities in unborn repositories.
- Label Observer proof as recorded candidate evidence rather than a working-tree watch. Keep normal agent context scoped and avoid duplicate contract injection.

### Distribution and validation

- Publish matching Codex and Claude Code 3.8.0 manifests from `main`, with repository-backed installation/update instructions for both hosts.
- Pass 120 regression tests, including bound proof, reuse, malformed inputs, replan invalidation, pause/resume, expansion, archive/reset/restore, legacy adoption and live visualization.

## 3.7.1

- Harden history semantics and cross-record validation, recover interrupted chronicle appends, and require evidence for claimed replay fidelity.
- Surface exact Git binding as established, pending, optional or unavailable rather than inferring provenance.

## 3.7.0

### Cross-intent implementation chronicles

- Add a separate append-only `.pyramid/history` ledger with immutable intent-start, completion or inactive-archive chronicle, and clean Git code-binding records.
- Preserve the ledger across archive, reset, restore, reopen, and new-intent cycles without adding historical nodes or states to the active graph.
- Reject historical plan-ID reuse before lifecycle mutation and validate record hashes, order, and chain identity.

### Human and agent observability

- Add `pyramid-task:history` and bounded CLI queries by intent, repository path, Git commit, or read-only replay context.
- Add a History Observer beside the active Intent Observer and Technical graph, focused on purpose, demonstrated path, turning points, ending rationale, provenance coverage, and replay fidelity.
- Keep replay calibrated as partial, behaviorally equivalent, or artifact-identical; require a clean descendant Git commit whose material range exactly matches task-declared files before exact binding.

### Contracts and packaging

- Publish history head, start, chronicle, binding, index, and visualization-v3 schemas with lifecycle and architecture guidance.
- Carry exact task changed-file declarations into intent provenance and make missing evidence visible rather than inferred.

## 3.6.0

### Human-first intent observation

- Replace the graph-first landing page with an Intent Observer that leads with intent, last verified outcome, next proof, active work, interventions, recommended action, and selected-path structure.
- Derive the observer as a deterministic read model from validated graph and audit state; keep canonical plan and runtime schemas unchanged.
- Separate implementation checks, acceptance checks, and audit proof, and keep raw IDs, graph metadata, topology layouts, and assurance overlays in the Technical graph drill-down.

### Demonstrable increments

- Start plan creation from the current demonstrable baseline and the smallest honest ladder of usable states to the final intent.
- Represent every increment with existing outcome and `validated-by` audit primitives, make each later gate depend on the previous verified increment outcome, and require current inherited proof instead of treating historical passes as regression evidence.
- Teach create, simplify, replan, audit, inspect, expand, orchestrate, and visualize to preserve increment boundaries while keeping `level`, `wave`, parallel batches, and delivery acceptance distinct.
- Keep the plan schema and runtime state backward-compatible; this is a shared planning and audit contract rather than a new node kind or mutable status.

### Snapshot-safe intra-task helpers

- Let a claimed implementation task use spare host-agent slots for bounded research, reconnaissance, review, and validation while preserving one canonical coordinator.
- Bind helper jobs and results to immutable snapshots, narrow read scopes, acceptance criteria, explicit join boundaries, prohibitions, and context budgets through published schemas.
- Prioritize independently auditable graph-task workers, isolate write-producing checks, reject helper source mutations, and promote candidate evidence only when its snapshot matches the accepted result.
- Keep evidence-only audit events in scoped mutation guards without making product inspections stale unless an inspection explicitly declares evidence changes as invalidating.

### Evidence-based plan refinement

- Add the `pyramid-task:simplify` skill and require a semantic refinement pass before candidate creation, new-intent transition, or replan preview.
- Fact-check load-bearing claims, trace intent requirements in both directions, challenge duplicate or speculative graph structure, and preserve justified no-change outcomes.
- Publish `pyramid-plan-review-v1` for facts, counterevidence, findings, coverage, invariants, before/after metrics, and limitations without treating the review as self-proving evidence.

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
