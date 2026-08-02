# Brownfield Change-Assurance Contract

Pyramid Task V3 treats work in an existing system as change assurance, not only task decomposition. The graph still states how the intended outcome should be established. The assurance bundle states what already exists, what may be affected, how that scope was inspected, and what evidence permits the change to advance.

## Project mode

`.pyramid/project.json` declares format version 3 and either `greenfield` or `brownfield` mode. `create --mode auto` selects brownfield when the project root already contains meaningful files. Use an explicit mode only when repository evidence makes the automatic choice wrong.

Legacy projects without `project.json` remain readable. Upgrade them through the upgrade contract before using brownfield enforcement.

## Baseline

`.pyramid/baseline.json` is the system's change baseline—the equivalent of a vehicle registration plus service history. It contains:

- stable assets with kind, owner, criticality, locators, confidence, and evidence;
- typed relations between assets;
- relevant incidents, defects, migrations, decisions, workarounds, and past changes;
- explicit unknowns and a status of `incomplete`, `current`, or `stale`.

Model assets at the narrowest boundary useful for impact and inspection. A repository-root placeholder is valid for discovery but cannot authorize an audit pass because an incomplete baseline is a blocker. Preserve historical assets when assurance records still reference them.

## Assurance bundle

`.pyramid/assurance.json` contains:

- impacts mapping graph task IDs to affected assets, with direct or transitive paths, confidence, status, and evidence;
- inspections mapping assets and tasks to methods, results, sufficiency, limitations, and evidence;
- findings with severity and accountable disposition;
- scope-drift records comparing declared impact with actual changed files or assets;
- rollback and monitoring controls;
- a legacy bridge for evidence that could not be represented before V3;
- staleness reasons and the graph version at which enforcement begins.

An impact hypothesis is not confirmed evidence. A passing inspection is not sufficient unless its scope and limitations cover the load-bearing risk. A high or critical open finding blocks affected audits. Accepted findings need an accountable actor and reason.

## Enforcement

A brownfield audit pass must include an `assurance` assertion that names the impact, inspection, and finding records reviewed and marks the scope review complete. The runtime checks the assertion against canonical assurance data; an agent cannot satisfy it by listing invented IDs.

The final intent additionally requires a current baseline, confirmed impact coverage, sufficient passing inspections for every impacted asset, resolved scope drift, dispositioned material findings, rollback and monitoring controls, and any required legacy bridge.

## Invalidation

Evidence becomes stale when its scope premise changes. Baseline reassessment stales performed inspections. Replan, approved expansion, reopen, audit failure, and undeclared implementation scope stale affected assurance and dependent verification. Reconcile by updating the canonical baseline or assurance bundle through `assess` or `impact`, never by editing generated views or weakening an audit.

Workers report both `changed_files` and, when known, `changed_assets`. The runtime compares them with confirmed or hypothesized impact records. An unmapped change creates an open drift record and blocks audit until evidence maps or dismisses it.

## Closure and carry-forward

Closing a brownfield plan writes a JSON and Markdown change dossier containing predicted impact, actual changed files and assets, scope-drift reconciliation, inspections, findings, audits, controls, residual risk, legacy bridge, and the baseline before and after the change. It advances the baseline revision so the verified changed system becomes the starting point for the next plan.

Reset archives the current plan but carries the current baseline and prior dossiers into the new brownfield planning cycle. Archive, restore, and clean preserve the manifest, baseline, assurance, dossiers, and their evidence provenance.
