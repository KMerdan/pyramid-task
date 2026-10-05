---
name: replan
description: Replan an existing Pyramid Task V3 graph or demonstrable-increment ladder from new evidence, audit failure, invalid assumptions, architecture changes, or an explicitly changed intent. Use when topology, increment boundaries, or path selection must change while preserving valid work, state history, assurance provenance, and traceability.
---

# Replan a Pyramid Task Path

For additive file/context discoveries inside an unchanged owned task, first read only `../../references/task-amendments.md` and use `amend` if eligible. Do not load the full planning references or regenerate the plan for that path.

For a semantic or topology replan, read `../../references/graph-contract.md` and `../../references/plan-refinement.md`. Load `../../references/pathfinder-workflow.md` only for a changed path or load-bearing uncertainty; `../../references/demonstrable-increments.md` for changed increment/composition boundaries; `../../references/agent-contracts.md` for changed packet/result details; `../../references/brownfield-assurance.md` in brownfield mode; and `../../references/lifecycle-contract.md` when the plan is inactive. Reuse current references already in context.

Use `pyramid-task:expand` instead when a single executable task keeps the same purpose, contract, selected path, and external relations and only needs a deeper approved subtree.

Read `../../references/development-harness.md` when changing proof or adopting it in a legacy plan. Reuse sufficient procedures and add only capability required by the changed outcome. Preserve schema 2 once adopted. Explain invalidated shared proof and dependent claims, not only changed task text; regenerate the guide through guarded replan.

## Workflow

1. Capture the triggering evidence or audit result.
2. Confirm the plan lifecycle is active. Restore an archived plan or reopen affected completed work before replanning.
3. Start with affected node packets and bounded `diff` output. Inspect their dependency/proof consumers, relevant baseline and completed evidence; load the full canonical plan only to assemble the complete candidate. Do not reload unrelated source, logs or history. Capture current composite context before preview/apply.
4. Preserve nodes, historical increment passes, and evidence that remain valid. Mark replaced paths `superseded`; never erase history or present a historical pass as current regression evidence.
5. Re-run backward and forward path checks across the affected region. Start at the earliest invalid rung, preserve earlier verified rungs, and revise later acceptance and inherited proofs when a load-bearing assumption changes.
6. Write a complete candidate plan JSON. Confirm that changed increment outcomes remain actor-visible and form a justified cumulative ladder, each has its own gate, each later gate depends on the previous verified increment outcome and inherits earlier proofs, and any distinct final gate covers every direct intent branch. Run the evidence-based refinement pass, write a `pyramid-plan-review-v1` artifact, and preserve valid completed work, evidence, assurance, and history. Use `pyramid-task:simplify` when reduction or fact-checking is the primary trigger.
   Copy the current candidate and edit only affected stable IDs/fields. Preserve untouched wording/contracts; a full saved snapshot does not require broad redrafting. Keep actual start dependencies separate from audit/release ordering and keep each changed gate a complete promised public journey.
7. Preview the diff:

```bash
python3 ../../scripts/pyramid.py replan --project <project-root> --plan <candidate-plan.json> --actor <actor> --reason <reason> --preview --json
```

8. Report the material delta, invalidations and next action; reference the review artifact instead of repeating it. Obtain direction before a material intent change or scope expansion. Do not ask again for unchanged authority already granted. Stop refinement once coverage, evidence and safety are adequate; another pass needs a concrete unresolved finding. Supporting-context reuse never waives mandatory skill reads or candidate validation.
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
