# Changelog

All notable changes follow semantic versioning. Serialized task graph and state schemas keep their existing version where backward compatibility is preserved; the project manifest declares the V3 format.

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
