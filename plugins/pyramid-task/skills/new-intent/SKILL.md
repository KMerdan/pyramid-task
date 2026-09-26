---
name: new-intent
description: Safely start a fresh Pyramid Task intent when no plan exists or after a V3 plan has completed. Use for another feature, intent or task cluster while preserving finished work, carrying the brownfield baseline, archiving the old graph and obtaining approval before reset.
---

# Start a New Pyramid Intent

Use the runtime's hash-bound transition instead of choosing `create`, `archive`, and `reset` by inference. The runtime preserves the prior intent chronicle and captures the new intent's source starting point automatically.

## Context routing

Read `../../references/new-intent-contract.md`. Load `../../references/lifecycle-contract.md` only when a current plan exists, and `../create/SKILL.md` only while drafting the new candidate plan.

## Workflow

1. Run `doctor --json`. Treat `.pyramid/project.json`, not `plan.json` or `state.json`, as the V3 project-format marker.
2. Clarify, decompose, fact-check, and refine the new intent through the complete create workflow, but write only a temporary candidate plan and its `pyramid-plan-review-v1` artifact. Do not call `create` over an existing project and do not write generated `docs/tasks/` by hand.
3. Preview the lifecycle transition:

```bash
python3 ../../scripts/pyramid.py new-intent --project <project-root> --plan <candidate-plan.json> --actor <actor> --reason <reason> --mode auto --preview --json
```

4. If the preview is blocked, preserve the current plan and explain the reported action. Never silently replace active work or active claims.
5. If approval is required, explain the current format and lifecycle, exact transition, preserved evidence, baseline behavior, blockers, and transition hash. Ask the user to approve that preview.
6. Apply only with the approved hash and provenance:

```bash
python3 ../../scripts/pyramid.py new-intent --project <project-root> --plan <candidate-plan.json> --actor <actor> --reason <reason> --mode auto --apply --approved-by <user> --approval-reference <reference> --approved-new-intent-sha256 <preview-hash> --expected-version <graph-version> --expected-context <context-id> --json
```

7. Run `validate`, `doctor`, and `inspect --summary`. Report the previous archive and chronicle, carried baseline, new plan ID, ready frontier, and remaining assurance gaps. Never reuse a historical `plan_id`; restore its archive instead.

## Authority

- Pyramid Task V3 owns `.pyramid` state and generated `docs/tasks/` projections.
- `plan.json` and `state.json` are stable cross-version contracts; their presence does not make the installed runtime V2.
- An existing plan without a valid V3 `.pyramid/project.json` is unsupported. Preserve it and report the error; do not fabricate a manifest, migrate, reset or overwrite it.
- If a standalone `pyramid-task-planner` skill also triggers, use it only as a compatibility router. Never follow its obsolete direct-file-writing workflow.
