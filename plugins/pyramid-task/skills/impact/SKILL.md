---
name: impact
description: Map Pyramid Task V3 graph work to affected brownfield assets, plan or record inspections, manage findings and scope drift, and establish rollback and monitoring controls. Use before brownfield audit, after baseline changes, or whenever implementation scope differs from predicted impact.
---

# Analyze and Reconcile Change Impact

Read `../../references/brownfield-assurance.md`, `../../references/graph-contract.md`, and `../../references/agent-contracts.md` completely before impact analysis. Follow `../../schemas/assurance.schema.json`; use `../../assets/example-assurance.json` only as a structural example.

## Workflow

1. Inspect the current baseline, graph, relevant history, and existing assurance:

```bash
python3 ../../scripts/pyramid.py inspect --project <project-root> --assurance --json
```

2. Map each executable change and joint gate to directly or transitively affected assets. Record the dependency path, confidence, status, and evidence. Preserve hypotheses until evidence confirms or dismisses them.
3. Define risk-sensitive inspections for every impacted asset. Record method, required flag, performed result, sufficiency, evidence, and limitations. Add findings and give material findings an explicit resolved or accountable accepted disposition.
4. Establish evidenced rollback and monitoring controls or explain why either is not applicable.
5. Reconcile open drift only when evidence maps the actual changed file or asset to an impact record. Repeat stale inspections whose scope premise changed. Complete a required legacy bridge with targeted sufficient inspections.
6. Preview and apply the complete assurance candidate:

```bash
python3 ../../scripts/pyramid.py impact --project <project-root> --assurance <assurance.json> --actor <actor> --preview --json
python3 ../../scripts/pyramid.py impact --project <project-root> --assurance <assurance.json> --actor <actor> --apply --expected-version <graph-version> --json
```

7. Report canonical blockers, ready status, unresolved uncertainty, drift, material findings, and which audits the bundle covers.

## Boundaries

- Do not treat no discovered defect as proof that inspection was sufficient.
- Do not mark an impact confirmed without evidence or hide unpredicted scope.
- Do not accept high or critical findings without an accountable actor and rationale.
- Do not invent inspection output, rollback evidence, or monitoring coverage.
