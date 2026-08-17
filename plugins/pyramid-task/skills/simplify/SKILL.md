---
name: simplify
description: Review and simplify a generated or existing Pyramid Task V3 plan with evidence-backed fact checks while preserving intent, success evidence, safety, and assurance. Use after drafting a candidate plan, when the user asks to reduce or fact-check task-graph complexity, when nodes or dependencies appear duplicated or speculative, or before routing an existing canonical plan through replan.
---

# Simplify a Pyramid Task Plan

Reduce unjustified graph complexity without weakening the outcome or its proof.

## Context routing

Read `../../references/plan-refinement.md`, `../../references/pathfinder-workflow.md`, and `../../references/graph-contract.md`. Follow `../../schemas/plan-review.schema.json`; use `../../assets/example-plan-review.json` only as structure. Read `../../references/brownfield-assurance.md` for an existing system and `../replan/SKILL.md` before changing a canonical graph.

## Workflow

1. Identify whether the input is a temporary candidate or a canonical plan. Keep all candidate edits outside `.pyramid`; inspect canonical state with `doctor` and `inspect`.
2. Re-read the source intent, plan evidence, repository evidence, baseline, assurance, decisions, and applicable history. Separate observed facts, sourced claims, assumptions, and unknowns.
3. Fact-check load-bearing node and edge claims. Inspect exact files, symbols, call sites, tests, schemas, history, and authoritative sources. Seek contradictions and record freshness and limitations. Treat tests, docs, prior plans, and the reviewer's own assertions as evidence to inspect, not truth by default.
4. Trace both directions: every primary node must support an intent requirement, and every intent requirement must retain an implementation and evidence path.
5. Test the graph for duplicated work or evidence, speculative scope, unsupported claims, unjustified dependencies or gates, accidental serialization, ambiguous acceptance, and over- or under-decomposition. Challenge each candidate with its strongest reason to retain the current design.
6. Write a `pyramid-plan-review-v1` artifact. Record facts, findings, counterevidence, dispositions, requirement coverage, before/after metrics, preserved invariants, and limitations. A valid artifact records the reasoning; it does not make the semantic claims true by itself.
7. Apply only equivalence-preserving reductions to a temporary revised plan. Re-run the pathfinder audit and graph validation. Promote an unsupported load-bearing claim to an assumption, research node, or blocker instead of deleting the uncertainty.
8. For a new candidate, pass the revised plan into `create` or `new-intent`. For a canonical graph, produce the revised candidate and review first, then use `replan --preview`; obtain user direction before applying a topology, scope, or intent change.
9. Report applied, rejected, deferred, and blocking findings; before/after complexity; preserved assurance; and unresolved limitations. Report a justified no-change result when no safe simplification exists.

## Boundaries

- Optimize justified graph complexity, not node count.
- Never remove success evidence, constraints, non-goals, risk controls, compatibility, rollback, monitoring, inspections, or audit closure merely to make the graph smaller.
- Never convert an implementation task into its own independent audit.
- Never collapse tasks whose effects, ownership, write scopes, evidence contracts, or failure boundaries are materially distinct.
- Never silently rewrite canonical history. Preserve valid work and mark replaced paths `superseded` through replan.
- Ask before a proposed reduction changes product behavior, accepted risk, final intent, or material scope.
