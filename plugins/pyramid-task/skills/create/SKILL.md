---
name: create
description: Create a Pyramid Task V2 project from an intent, idea, feature, product design, or architecture proposal. Use when Codex must clarify the desired outcome, gather repository or external evidence, compare feasible paths, construct a hierarchical pathfinder graph, insert audit gates, and materialize agent-ready task files.
---

# Create a Pyramid Task Plan

Create a plan only after the intended final state is clear enough to test. Treat the plan as a claim-and-evidence graph, then project the selected path into a task pyramid.

## Required references

Read these files completely before planning:

- `../../references/pathfinder-workflow.md`
- `../../references/graph-contract.md`
- `../../references/agent-contracts.md`
- `../../references/lifecycle-contract.md`

Use `../../assets/example-plan.json` as a structural example, never as product evidence.

## Workflow

1. Read the source request, repository shape, existing plans, tests, schemas, and constraints.
2. Normalize the intent into actors, target state, success evidence, invariants, constraints, non-goals, and assumptions. Ask only about ambiguities that would materially change the path; otherwise record the assumption.
3. Gather evidence. Separate observed facts, sourced claims, assumptions, and unknowns. Turn a critical unknown into a research or decision node.
4. Backward-chain from the intent to required outcomes. Forward-chain from the current state to feasible work. Reconcile both chains.
5. Compare material alternatives by evidence strength, constraint fit, risk, reversibility, dependency burden, and testability. Preserve rejected alternatives and rationale.
6. Create a graph in a temporary JSON file that follows `graph-contract.md`. Use outcome nodes for required states and executable nodes for work. Add a joint audit wherever multiple branches compose.
7. Ensure each executable node has bounded scope, agent context, deliverables, acceptance criteria, and evidence requirements.
8. Run:

```bash
python3 ../../scripts/pyramid.py create --project <project-root> --plan <candidate-plan.json> --actor <actor>
```

9. Run `validate` and inspect the ready frontier. Fix the candidate plan and recreate only when creation failed before committing any project state. Use `reset`, never `create --force`, when a project already exists.
10. Summarize the intent, selected path, levels, ready tasks, audit gates, rejected alternatives, and important assumptions.

## Boundaries

- Let reasoning choose and explain the path. Let the runtime enforce schemas, cycles, references, readiness, transitions, events, and generated files.
- Do not hand-edit `.pyramid/state.json`, `.pyramid/graph.json`, `.pyramid/ready.json`, claims, or events.
- Do not claim that research proves a link when it only suggests one. Lower confidence or add a validation node.
- Do not make an implementation task double as its independent joint audit.
- Do not treat generated task completion as proof that the parent outcome is verified.
- Do not delete or overwrite an existing graph to restart; archive and reset it through lifecycle.
