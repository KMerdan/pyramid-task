---
name: assess
description: Build or refresh the evidence-backed baseline of an existing software system for a Pyramid Task V3 brownfield project. Use when .pyramid/baseline.json is incomplete or stale, repository assets and dependencies must be mapped, or historical incidents and controls must be recorded before impact analysis.
---

# Assess a Brownfield System

Read `../../references/brownfield-assurance.md`, `../../references/pathfinder-workflow.md`, and `../../references/graph-contract.md` completely before assessment. Follow `../../schemas/baseline.schema.json`; use `../../assets/example-baseline.json` only as a structural example.

## Workflow

1. Inspect the repository, architecture, tests, deployments, runbooks, ownership records, and relevant change or incident history. Separate observed evidence from assumptions and unknowns.
2. Model stable assets and typed relations at boundaries useful for impact analysis. Record locators that can classify actual changed files. Give criticality and confidence evidence, not intuition.
3. Preserve assets still referenced by assurance. Represent removal or replacement through history until impact records are reconciled.
4. Write a complete `pyramid-baseline-v1` candidate. Use `current` only when critical boundaries and unknowns are sufficiently understood; otherwise keep it `incomplete`.
5. Preview and then apply:

```bash
python3 ../../scripts/pyramid.py assess --project <project-root> --baseline <baseline.json> --actor <actor> --preview --json
python3 ../../scripts/pyramid.py assess --project <project-root> --baseline <baseline.json> --actor <actor> --apply --expected-version <graph-version> --json
```

6. Report revision, assets, relations, history, unknowns, and inspections made stale by the new baseline. Continue with `pyramid-task:impact`.

## Boundaries

- Do not mark a placeholder inventory current.
- Do not infer dependency or ownership certainty from filenames alone.
- Do not erase inconvenient incidents, workarounds, or unknowns.
- Do not hand-edit canonical state after apply.
