---
name: create
description: Create the first Pyramid Task V3 project from an intent, idea, feature, product design, or architecture proposal when no canonical plan exists. Use when the agent must clarify the desired outcome, assess an existing system, gather evidence, compare feasible paths, construct a hierarchical pathfinder graph, insert audit gates, and materialize agent-ready task files with brownfield assurance by default. Use `pyramid-task:new-intent`, not this skill, when `.pyramid/plan.json` already exists and the user wants another intent.
---

# Create a Pyramid Task Plan

Create a plan only after the intended final state is clear enough to test. Treat the plan as a claim-and-evidence graph, then project the selected path into a task pyramid.

## Context routing

Read `../../references/pathfinder-workflow.md` and `../../references/graph-contract.md` for graph construction. Read `../../references/agent-contracts.md` when defining executable packets. Read `../../references/brownfield-assurance.md` only for an existing system. Read `../../references/lifecycle-contract.md` only when an existing plan requires routing to another skill.

Use `../../assets/example-plan.json` as a structural example, never as product evidence.

## Workflow

1. Read the source request, repository shape, existing plans, tests, schemas, history, and constraints. Run `doctor --json` when `.pyramid/plan.json` exists. Use `pyramid-task:new-intent` for another intent; use `pyramid-task:upgrade` only when continuing the same legacy intent.
2. Normalize the intent into actors, target state, success evidence, invariants, constraints, non-goals, and assumptions. Ask only about ambiguities that would materially change the path; otherwise record the assumption.
3. Gather evidence. Separate observed facts, sourced claims, assumptions, and unknowns. For an existing system, build a `pyramid-baseline-v1` asset, relation, history, ownership, and unknown ledger; use `pyramid-task:assess` when this needs a dedicated pass.
4. Backward-chain from the intent to required outcomes. Forward-chain from the current state to feasible work. Reconcile both chains.
5. Compare material alternatives by evidence strength, constraint fit, risk, reversibility, dependency burden, and testability. Preserve rejected alternatives and rationale.
6. Create a graph in a temporary JSON file that follows `graph-contract.md`. Use outcome nodes for required states and executable nodes for work. Add a joint audit wherever multiple branches compose.
7. Ensure each executable node has bounded scope, agent context, deliverables, acceptance criteria, and evidence requirements. For brownfield work, create `pyramid-assurance-v1` impact hypotheses, required inspections, material finding policy, rollback, and monitoring controls; use `pyramid-task:impact` for a dedicated pass.
8. Run:

```bash
python3 ../../scripts/pyramid.py create --project <project-root> --plan <candidate-plan.json> --actor <actor> --mode auto --baseline <baseline.json> --assurance <assurance.json> --json
```

9. Omit baseline and assurance inputs only when an incomplete placeholder is honest; complete assessment and impact analysis before a brownfield audit can pass.
10. Run `validate` and inspect the ready frontier plus assurance blockers. Fix candidates and recreate only when creation failed before committing project state. Use `reset`, never `create --force`, when a project already exists.
11. Summarize the intent, selected path, levels, ready tasks, audit gates, affected assets, inspection gaps, rejected alternatives, and assumptions.

## Boundaries

- Let reasoning choose and explain the path. Let the runtime enforce schemas, cycles, references, readiness, transitions, events, and generated files.
- Do not hand-edit `.pyramid/state.json`, `.pyramid/graph.json`, `.pyramid/ready.json`, claims, or events.
- Do not claim that research proves a link when it only suggests one. Lower confidence or add a validation node.
- Do not make an implementation task double as its independent joint audit.
- Do not treat generated task completion as proof that the parent outcome is verified.
- Do not delete or overwrite an existing graph to restart; archive and reset it through lifecycle.
- Do not classify an existing repository as greenfield merely to bypass assurance.
- Treat `.pyramid/project.json` as the V3 project-format marker. `plan.json` and `state.json` remain canonical across versions and do not identify the installed runtime.
- If a standalone `pyramid-task-planner` skill also triggers, Pyramid Task V3 owns canonical state and generated task projections; ignore obsolete instructions to write `docs/tasks/` directly.
