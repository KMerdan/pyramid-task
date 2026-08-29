---
name: replan
description: Replan an existing Pyramid Task V3 graph or demonstrable-increment ladder from new evidence, audit failure, invalid assumptions, architecture changes, or an explicitly changed intent. Use when topology, increment boundaries, or path selection must change while preserving valid work, state history, assurance provenance, and traceability.
---

# Replan a Pyramid Task Path

Read `../../references/pathfinder-workflow.md`, `../../references/demonstrable-increments.md`, `../../references/plan-refinement.md`, and `../../references/graph-contract.md`. Load `../../references/agent-contracts.md` only for changed executable contracts, `../../references/brownfield-assurance.md` only in brownfield mode, and `../../references/lifecycle-contract.md` only when the plan is not active.

Use `pyramid-task:expand` instead when a single executable task keeps the same purpose, contract, selected path, and external relations and only needs a deeper approved subtree.

## Workflow

1. Capture the triggering evidence or audit result.
2. Confirm the plan lifecycle is active. Restore an archived plan or reopen affected completed work before replanning.
3. Inspect affected nodes, the current demonstrable baseline, increment outcomes and gates, descendants, alternatives, completed evidence, and the current graph version.
4. Preserve nodes, historical increment passes, and evidence that remain valid. Mark replaced paths `superseded`; never erase history or present a historical pass as current regression evidence.
5. Re-run backward and forward path checks across the affected region. Start at the earliest invalid rung, preserve earlier verified rungs, and revise later acceptance and inherited proofs when a load-bearing assumption changes.
6. Write a complete candidate plan JSON. Confirm that changed increment outcomes remain actor-visible and form a justified cumulative ladder, each has its own gate, each later gate depends on the previous verified increment outcome and inherits earlier proofs, and any distinct final gate covers every direct intent branch. Run the evidence-based refinement pass, write a `pyramid-plan-review-v1` artifact, and preserve valid completed work, evidence, assurance, and history. Use `pyramid-task:simplify` when reduction or fact-checking is the primary trigger.
7. Preview the diff:

```bash
python3 ../../scripts/pyramid.py replan --project <project-root> --plan <candidate-plan.json> --actor <actor> --reason <reason> --preview --json
```

8. Explain added, changed, merged, split, superseded, and newly blocked or ready nodes and increments. Obtain direction before a material intent change or scope expansion.
9. Apply the approved revision. Brownfield replan stales affected inspections and assurance; run `pyramid-task:impact` to map new and changed tasks before their audits:

```bash
python3 ../../scripts/pyramid.py replan --project <project-root> --plan <candidate-plan.json> --actor <actor> --reason <reason> --apply --expected-version <graph-version> --expected-context <context-id> --json
```

Use `--allow-intent-change` only when the user explicitly approved changing the final intent identifier.

## Boundaries

- Do not rewrite the plan through `update`.
- Do not invalidate verified work without citing the evidence or contract change that invalidates it.
- Do not weaken a failed increment gate or discard its historical evidence merely to preserve a schedule.
- Do not delete rejected or superseded alternatives needed to explain plan history.
- Do not treat lower node count as evidence of a better replan.
- Always preview before applying a material replan.
