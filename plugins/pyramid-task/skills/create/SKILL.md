---
name: create
description: Create the first Pyramid Task V3 project from an intent, idea, feature, product design, or architecture proposal when no canonical plan exists. Use when the agent must clarify the desired outcome, design an evidence-backed ladder of demonstrable increments, assess an existing system, compare feasible paths, construct a hierarchical pathfinder graph, insert audit gates, and materialize agent-ready task files with brownfield assurance by default. Use `pyramid-task:new-intent`, not this skill, when `.pyramid/plan.json` already exists and the user wants another intent.
---

# Create a Pyramid Task Plan

Create a plan only after the intended final state is clear enough to test. Begin with the current demonstrable baseline and the smallest honest ladder of usable states to that intent, then decompose the ladder into a claim-and-evidence task pyramid.

Read `../../references/development-harness.md` while defining proof. Create schema-2 plans with minimal outcome-scoped external, internal and applicable visual observations; reuse current tools and checks and add only missing capability before acceptance. Use `../../assets/example-harness-plan.json` for the current contract; the schema-1 example covers unbound verification within V3, not V2 project support.

## Context routing

Read `../../references/graph-contract.md` for graph construction and `../../references/plan-refinement.md` when the candidate is ready for review. Together with the harness contract above, these are the core planning references; do not preload all workflows.

- Read `../../references/pathfinder-workflow.md` when a load-bearing uncertainty or competing architecture needs a deeper path comparison.
- Read `../../references/demonstrable-increments.md` when designing multiple increments, composition or delivery-environment boundaries. The graph contract covers a simple single-increment plan.
- Read `../../references/agent-contracts.md` only for packet/result details not covered by the graph and harness contracts.
- Read `../../references/brownfield-assurance.md` for an existing system; read `../../references/lifecycle-contract.md` only when an existing plan requires lifecycle routing.

Reuse current facts and references already in context; reopen them when missing or changed. Inspect the smallest repository region that establishes scope, dependencies and proof. Do not copy entire examples, logs or history into reasoning or reports. Examples show structure, never product evidence.

## Workflow

1. Read the source request, repository shape, existing plans, tests, schemas, history, and constraints. Run `doctor --json` when `.pyramid/plan.json` exists. Use `pyramid-task:new-intent` for another intent. An existing plan requires a valid V3 project manifest; report unsupported legacy data without replacing it or inventing a migration.
2. Normalize the intent into actors, target state, success evidence, invariants, constraints, non-goals, and assumptions. Ask only about ambiguities that would materially change the path; otherwise record the assumption.
3. Gather evidence for the affected path. Separate observed facts, sourced claims, assumptions, and unknowns. Reuse a current brownfield baseline and inspect affected assets; build or refresh it with `pyramid-task:assess` only where missing or stale. Stop discovery when load-bearing claims are evidenced, explicitly assumed with early validation, or blocked; do not survey unrelated subsystems.
4. Define the current demonstrable baseline and the smallest evidence-supported increment ladder. For software, each rung should build or launch and complete a meaningful actor-visible scenario. Record the baseline, ordered ladder, and rejected slicing alternatives in a selected-path decision backed by evidence. Keep one increment when no smaller honest state exists; never call setup alone an increment.
   Make the first gate prove the smallest complete promised public journey, not a component matrix, process start or harness installation. A probe/capture setup task must precede the acceptance that consumes it, not unrelated product work.
5. Backward-chain from the intent through the ladder to required outcomes. Forward-chain from the current baseline to feasible work and proof. Reconcile both chains. Shape sibling work as independently reviewable outcomes where the evidence supports it: minimize unnecessary hard dependencies, assign genuinely independent branches the same earliest safe wave, keep scopes disjoint, and add one joint audit for their composition. Do not persist parallel groups; the runtime derives them from live readiness.
   Use a hard start dependency only for an actual consumed artifact, contract or state. Use integration/validation ordering for evidence consumed at audit; release constraints do not serialize independent implementation.
6. Compare material alternatives by evidence strength, constraint fit, risk, reversibility, dependency burden, increment quality, and testability. Preserve rejected alternatives and rationale.
7. Create a graph in a temporary JSON file that follows `graph-contract.md`. Represent each increment as a primary outcome with its own `validated-by` audit gate. Prefer a cumulative outcome chain ending at the intent; make each later gate depend on the previous verified increment outcome and re-establish inherited observable behavior. Add a separate final gate only for additional direct intent branches or distinct release-level composition evidence. Use executable nodes for work and add a joint audit wherever multiple branches compose.
8. Ensure each executable node has bounded scope, agent context, deliverables, acceptance criteria, and evidence requirements and traces to the earliest increment it establishes or safely enables. Declare `agent.effect`, evidence output globs, and generated output globs with asset IDs when applicable. For brownfield work, create narrow `pyramid-assurance-v1` impact hypotheses and inspections; give broad boundary or release inspections an explicit `pre-audit` or `release` refresh policy and declare which change classes invalidate them. Add material finding policy, rollback, and monitoring controls; use `pyramid-task:impact` for a dedicated pass.
9. Run the evidence-based refinement pass on the complete temporary candidate before making it canonical. Fact-check load-bearing claims and edges, test bidirectional requirement and increment coverage, challenge duplicate, speculative, horizontal, or artificial work, and write a `pyramid-plan-review-v1` artifact against `../../schemas/plan-review.schema.json`. Revise only when intent, demonstrable value, evidence, safety, and assurance remain preserved. Use `pyramid-task:simplify` for a dedicated pass.
10. Run:

```bash
python3 ../../scripts/pyramid.py create --project <project-root> --plan <candidate-plan.json> --actor <actor> --mode auto --baseline <baseline.json> --assurance <assurance.json> --json
```

11. Omit baseline and assurance inputs for genuine greenfield projects. In brownfield mode, permit an incomplete placeholder only when honest; complete assessment and impact analysis before an audit can pass.
12. Run `validate` and inspect the ready frontier plus assurance blockers. Confirm that the increment outcomes form a justified ladder, every increment has its gate, later gates inherit prior proofs, and no wave is being reported as delivery evidence. When parallel execution is useful, also run `inspect --parallel-ready --max-agents <slots>` to confirm that intended sibling branches are actually independent. Fix candidates and recreate only when creation failed before committing project state. Use `reset`, never `create --force`, when a project already exists.
13. Report the selected path, next demonstrable gate, ready work, material unknowns and evidence locations. Keep the complete reasoning in the plan/review artifacts, not repeated in the handoff. The runtime creates the immutable intent-start record; do not write history manually.

## Boundaries

- Let reasoning choose and explain the path. Let the runtime enforce schemas, cycles, references, readiness, transitions, events, and generated files.
- Do not hand-edit `.pyramid/state.json`, `.pyramid/graph.json`, `.pyramid/ready.json`, claims, or events.
- Do not claim that research proves a link when it only suggests one. Lower confidence or add a validation node.
- Do not optimize task count or treat a review artifact as proof of its own factual claims.
- Do not confuse an execution wave, component milestone, or implemented task set with a demonstrable increment.
- Do not force multiple increments when the evidence supports only one honest usable state.
- Do not make an implementation task double as its independent joint audit.
- Treat routine agent review as review, not a new human approval requirement. Ask the human only for material ambiguity, new authority, irreversible/high-impact effects or unresolved consequential risk. Review never replaces missing technical proof.
- Do not treat generated task completion as proof that the parent outcome is verified.
- Do not delete or overwrite an existing graph to restart; archive and reset it through lifecycle.
- Do not classify an existing repository as greenfield merely to bypass assurance.
- Treat `.pyramid/project.json` as the V3 project-format marker. `plan.json` and `state.json` remain canonical across versions and do not identify the installed runtime.
- If a standalone `pyramid-task-planner` skill also triggers, Pyramid Task V3 owns canonical state and generated task projections; ignore obsolete instructions to write `docs/tasks/` directly.
