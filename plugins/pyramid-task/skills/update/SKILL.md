---
name: update
description: Record progress, blockers, risk, release, or implementation completion for a claimed Pyramid Task V3 node. Use when a worker agent must submit structured results, changed files and assets, and evidence without changing graph topology or declaring the parent outcome verified.
---

# Update a Pyramid Task

Read `../../references/agent-contracts.md` when constructing a result or resolving a contract question, not for a simple health/release update with a current packet. Load `../../references/brownfield-assurance.md` only when reporting changed assets or drift, and `../../references/lifecycle-contract.md` only if the plan is inactive.

When submitting harness evidence, follow `../../references/development-harness.md`: submit performed observations and hashed artifacts or valid run references with the existing result. Reuse the contract already in context; a health/release update does not require another harness read or test run. Never refresh a pre-run fingerprint after checking to disguise changed inputs. Stage evidence outside `.pyramid`; the update imports it. Keep failed/unperformed checks visible.

## Workflow

1. Confirm the actor owns the active claim and the task packet is current.
   For health-only reporting, reuse the current packet/guard. Do not capture new proof or run tests merely to report health. If the guard conflicts, inspect this node and reconcile the changed facts before retrying; never repeat a successful mutation to obtain detail.
2. For implementation or evidence submissions, run the required checks unless current candidate-bound evidence can be reused. Record actual commands, outcomes, every changed file, known `changed_assets`, acceptance evidence, risks, and proposed graph changes in `agent-result-v1` JSON. A simple health/release update needs no new test run. These exact declarations become the intent chronicle's task-to-code provenance; never omit an implementation file. Classify authored, generated, runtime, configuration, evidence, and unknown changes only when classification matters. Use `change_effect: evidence-only` only for files inside the task's declared evidence output scope. Generated files require a predeclared output pattern and asset mapping.
3. Apply exactly one transition using `mutation_guards.task`. CLI output is compact by default: fresh guards, blockers, dependencies and assurance without unchanged contract fields or duplicate event snapshots. Use `--full` only when the decision needs the complete response. If detail is missing afterward, inspect this node or the referenced event; never repeat a mutation to recover output. Full records remain on disk; take/resume always return the complete task packet.

```bash
python3 ../../scripts/pyramid.py update --project <project-root> --node TASK-203 --actor <actor> --status implemented --result <result.json> --expected-guard <task-guard> --json
python3 ../../scripts/pyramid.py update --project <project-root> --node TASK-203 --actor <actor> --status blocked --reason <reason> --result <result.json> --expected-guard <task-guard> --json
python3 ../../scripts/pyramid.py update --project <project-root> --node TASK-203 --actor <actor> --status at-risk --reason <reason> --expected-guard <task-guard> --json
python3 ../../scripts/pyramid.py update --project <project-root> --node TASK-203 --actor <actor> --status release --expected-guard <task-guard> --json
```

4. Report execution, verification, health, availability, detected scope drift, invalidated assurance, and remaining rework separately.
5. For eligible additive file/context discoveries, read `../../references/task-amendments.md` and use `amend` without releasing ownership. If the unchanged task contract needs internal decomposition, include `suggested_graph_changes`, release the claim, and use `expand`. Use `replan` when the contract, proof or selected path changed.

## Boundaries

- `implemented` means the worker finished the scoped work; it does not mean `verified`.
- Do not report tests as passed unless they were run successfully.
- Save complete test logs as evidence; return results, actionable failures and references rather than repeatedly injecting successful logs. Never omit failed attempts or required acceptance evidence to reduce output.
- Do not hand-edit state, claims, graph snapshots, or event files.
- Do not use this interface to add, remove, or reparent nodes.
- Never omit an out-of-scope changed file to avoid drift detection. Reconcile drift through `pyramid-task:impact`.
- Do not label source or generated behavior as evidence-only. The runtime rejects undeclared evidence and generated scopes and treats unknown changes conservatively.
