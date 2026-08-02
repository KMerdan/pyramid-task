---
name: new-intent
description: Safely start a fresh Pyramid Task intent when no plan exists or after a V2, V2.1, or V3 plan has completed. Use when the user asks for another feature, intent, or task cluster in a repository that already contains `.pyramid`, especially when the agent must preserve finished work, upgrade legacy state, carry the brownfield baseline, archive the old graph, and obtain approval before reset.
---

# Start a New Pyramid Intent

Use the runtime's hash-bound transition instead of choosing `create`, `upgrade`, and `reset` by inference.

## Required reading

Read these files completely:

- `../../references/new-intent-contract.md`
- `../../references/lifecycle-contract.md`
- `../../references/upgrade-contract.md`
- `../create/SKILL.md`

## Workflow

1. Run `doctor --json`. Treat `.pyramid/project.json`, not `plan.json` or `state.json`, as the V3 project-format marker.
2. Clarify and decompose the new intent through the create workflow, but write only a temporary candidate plan. Do not call `create` over an existing project and do not write generated `docs/tasks/` by hand.
3. Preview the lifecycle transition:

```bash
python3 ../../scripts/pyramid.py new-intent --project <project-root> --plan <candidate-plan.json> --actor <actor> --reason <reason> --from-version 2.1 --mode auto --preview --json
```

4. If the preview is blocked, preserve the current plan and explain the reported action. Never silently replace active work or active claims.
5. If approval is required, explain the current format and lifecycle, exact transition, preserved evidence, baseline behavior, blockers, and transition hash. Ask the user to approve that preview.
6. Apply only with the approved hash and provenance:

```bash
python3 ../../scripts/pyramid.py new-intent --project <project-root> --plan <candidate-plan.json> --actor <actor> --reason <reason> --from-version 2.1 --mode auto --apply --approved-by <user> --approval-reference <reference> --approved-new-intent-sha256 <preview-hash> --expected-version <graph-version> --json
```

7. Run `validate`, `doctor`, and `inspect --summary`. Report the previous archive, any pre-upgrade snapshot, carried baseline, new plan ID, ready frontier, and remaining assurance gaps.

## Authority

- Pyramid Task V3 owns `.pyramid` state and generated `docs/tasks/` projections.
- `plan.json` and `state.json` are stable cross-version contracts; their presence does not make the installed runtime V2.
- A project without `.pyramid/project.json` is legacy and the preview decides whether upgrade is required.
- If a standalone `pyramid-task-planner` skill also triggers, use it only as a compatibility router. Never follow its obsolete direct-file-writing workflow.
