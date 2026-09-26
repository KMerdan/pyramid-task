---
name: create
description: Create the first Pyramid Task V3 project from an intent, idea, feature, product design, or architecture proposal when no canonical plan exists. Use when the agent must clarify the desired outcome, design an evidence-backed ladder of demonstrable increments, assess an existing system, compare feasible paths, construct a hierarchical pathfinder graph, insert audit gates, and materialize agent-ready task files with brownfield assurance by default. Use `pyramid-task:new-intent`, not this skill, when `.pyramid/plan.json` already exists and the user wants another intent.
---

# Create a Pyramid Task Plan

Create a plan only after the intended final state is clear enough to test. Begin with the current demonstrable baseline and the smallest honest ladder of usable states to that intent, then decompose the ladder into a claim-and-evidence task pyramid.

Read `../../references/development-harness.md` while defining proof. Create schema-2 plans with minimal outcome-scoped external, internal and applicable visual observations; reuse current tools and checks and add only missing capability before acceptance. Use `../../assets/example-harness-plan.json` for the current contract; the schema-1 example is for legacy compatibility.

## Context routing

Read `../../references/pathfinder-workflow.md`, `../../references/demonstrable-increments.md`, `../../references/plan-refinement.md`, and `../../references/graph-contract.md` for graph construction and candidate refinement. Read `../../references/agent-contracts.md` when defining executable packets. Read `../../references/brownfield-assurance.md` only for an existing system. Read `../../references/lifecycle-contract.md` only when an existing plan requires routing to another skill.

Use `../../assets/example-plan.json` as a structural example, never as product evidence.

## Workflow

1. Read the source request, repository shape, existing plans, tests, schemas, history, and constraints. Run `doctor --json` when `.pyramid/plan.json` exists. Use `pyramid-task:new-intent` for another intent; use `pyramid-task:upgrade` only when continuing the same legacy intent.
2. Normalize the intent into actors, target state, success evidence, invariants, constraints, non-goals, and assumptions. Ask only about ambiguities that would materially change the path; otherwise record the assumption.
3. Gather evidence. Separate observed facts, sourced claims, assumptions, and unknowns. For an existing system, build a `pyramid-baseline-v1` asset, relation, history, ownership, and unknown ledger; use `pyramid-task:assess` when this needs a dedicated pass.
4. Define the current demonstrable baseline and the smallest evidence-supported increment ladder. For software, each rung should build or launch and complete a meaningful actor-visible scenario. Record the baseline, ordered ladder, and rejected slicing alternatives in a selected-path decision backed by evidence. Keep one increment when no smaller honest state exists; never call setup alone an increment.
5. Backward-chain from the intent through the ladder to required outcomes. Forward-chain from the current baseline to feasible work and proof. Reconcile both chains. Shape sibling work as independently reviewable outcomes where the evidence supports it: minimize unnecessary hard dependencies, assign genuinely independent branches the same earliest safe wave, keep scopes disjoint, and add one joint audit for their composition. Do not persist parallel groups; the runtime derives them from live readiness.
6. Compare material alternatives by evidence strength, constraint fit, risk, reversibility, dependency burden, increment quality, and testability. Preserve rejected alternatives and rationale.
7. Create a graph in a temporary JSON file that follows `graph-contract.md`. Represent each increment as a primary outcome with its own `validated-by` audit gate. Prefer a cumulative outcome chain ending at the intent; make each later gate depend on the previous verified increment outcome and re-establish inherited observable behavior. Add a separate final gate only for additional direct intent branches or distinct release-level composition evidence. Use executable nodes for work and add a joint audit wherever multiple branches compose.
8. Ensure each executable node has bounded scope, agent context, deliverables, acceptance criteria, and evidence requirements and traces to the earliest increment it establishes or safely enables. Declare `agent.effect`, evidence output globs, and generated output globs with asset IDs when applicable. For brownfield work, create narrow `pyramid-assurance-v1` impact hypotheses and inspections; give broad boundary or release inspections an explicit `pre-audit` or `release` refresh policy and declare which change classes invalidate them. Add material finding policy, rollback, and monitoring controls; use `pyramid-task:impact` for a dedicated pass.
9. Run the evidence-based refinement pass on the complete temporary candidate before making it canonical. Fact-check load-bearing claims and edges, test bidirectional requirement and increment coverage, challenge duplicate, speculative, horizontal, or artificial work, and write a `pyramid-plan-review-v1` artifact against `../../schemas/plan-review.schema.json`. Revise only when intent, demonstrable value, evidence, safety, and assurance remain preserved. Use `pyramid-task:simplify` for a dedicated pass.
10. Run:

```bash
python3 ../../scripts/pyramid.py create --project <project-root> --plan <candidate-plan.json> --actor <actor> --mode auto --baseline <baseline.json> --assurance <assurance.json> --json
```

11. Omit baseline and assurance inputs only when an incomplete placeholder is honest; complete assessment and impact analysis before a brownfield audit can pass.
12. Run `validate` and inspect the ready frontier plus assurance blockers. Confirm that the increment outcomes form a justified ladder, every increment has its gate, later gates inherit prior proofs, and no wave is being reported as delivery evidence. When parallel execution is useful, also run `inspect --parallel-ready --max-agents <slots>` to confirm that intended sibling branches are actually independent. Fix candidates and recreate only when creation failed before committing project state. Use `reset`, never `create --force`, when a project already exists.
13. Summarize the intent, captured source starting point, current demonstrable baseline, increment ladder and gates, selected path, refinement findings and metrics, levels, ready tasks, affected assets, inspection gaps, rejected alternatives, assumptions, and limitations. The runtime creates the immutable intent-start record; do not write history manually.

## Boundaries

- Let reasoning choose and explain the path. Let the runtime enforce schemas, cycles, references, readiness, transitions, events, and generated files.
- Do not hand-edit `.pyramid/state.json`, `.pyramid/graph.json`, `.pyramid/ready.json`, claims, or events.
- Do not claim that research proves a link when it only suggests one. Lower confidence or add a validation node.
- Do not optimize task count or treat a review artifact as proof of its own factual claims.
- Do not confuse an execution wave, component milestone, or implemented task set with a demonstrable increment.
- Do not force multiple increments when the evidence supports only one honest usable state.
- Do not make an implementation task double as its independent joint audit.
- Do not treat generated task completion as proof that the parent outcome is verified.
- Do not delete or overwrite an existing graph to restart; archive and reset it through lifecycle.
- Do not classify an existing repository as greenfield merely to bypass assurance.
- Treat `.pyramid/project.json` as the V3 project-format marker. `plan.json` and `state.json` remain canonical across versions and do not identify the installed runtime.
- If a standalone `pyramid-task-planner` skill also triggers, Pyramid Task V3 owns canonical state and generated task projections; ignore obsolete instructions to write `docs/tasks/` directly.
