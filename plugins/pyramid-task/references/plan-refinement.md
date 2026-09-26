# Evidence-Based Plan Refinement

Use this contract after drafting a complete candidate graph and before making it canonical. Use the same analysis on an existing graph, but route any canonical topology change through replan. Review a candidate once, then revisit only concrete unresolved findings or affected invariants after a correction. Do not run a second generic review or invent alternatives to fill a template. An eligible task amendment uses its narrow boundary review instead of this whole-plan artifact.

## Evidence standard

Classify every load-bearing claim as observed, sourced, assumption, or unknown. A fact reference must identify something another agent can inspect: a repository path and symbol, a test or schema, an event or incident, a decision record, or an authoritative external source with a freshness note. Read the referenced material and seek disconfirming evidence. Do not treat tests, documentation, historical plans, generated files, or an agent assertion as automatically current production truth.

An unsupported non-load-bearing detail may be removed or qualified. An unsupported load-bearing claim becomes an explicit assumption with early validation, a research task, or a blocker. Never manufacture confidence to keep the plan moving.

## Bidirectional trace

Check both directions:

1. Trace each primary node through typed edges and `source_requirements` to a stated intent requirement. Reject work that cannot justify its contribution.
2. Trace each intent requirement through demonstrable increment outcomes, executable work, required evidence, and audit closure. Reject a reduction that breaks this path or leaves a planned delivery cycle without an honest demonstrable state.

For brownfield work, also trace changed tasks through affected assets, inspections, findings, rollback, monitoring, and invalidation rules.

## Simplification classes

Inspect for:

- duplicate nodes, deliverables, acceptance criteria, evidence, or edges;
- speculative capabilities or future generality outside the intent;
- hard dependencies with no consumed artifact, contract, state, or evidence;
- audit gates without a real composition or independent-verification boundary;
- ceremonial increments with no distinct actor-visible value, proof, or recovery boundary;
- horizontal component phases that could form a smaller end-to-end demonstrable slice;
- later increment gates that do not repeat or otherwise establish inherited observable behavior;
- wrapper tasks that only restate another task;
- accidental serialization between disjoint tasks;
- over-decomposition that divides one bounded effect and evidence contract;
- under-decomposition that hides distinct effects, owners, scopes, or failure boundaries;
- unsupported repository or external claims;
- ambiguous acceptance criteria that cannot establish completion.

Map increment findings to the published review schema instead of inventing classes: use `unjustified-gate` for a ceremonial increment, `under-decomposition` for a horizontal phase that hides a feasible vertical slice, and `ambiguous-acceptance` for missing inherited proof. Use another existing class only when its definition fits the actual defect.

Splitting an unsafe task is corrective refinement, not a complexity reduction. Retain separate nodes when they protect distinct effects, ownership, contracts, write scopes, rollback boundaries, or independent evidence.

## Candidate decision test

For each finding:

1. State the proposed removal, merge, demotion, qualification, or dependency change.
2. Cite supporting evidence and the strongest counterevidence or retention rationale.
3. Compare behavior, requirement coverage, evidence quality, risk containment, reversibility, execution frontier, and brownfield assurance before and after.
4. Apply the change only when intent equivalence is clear and no assurance dimension weakens.
5. Mark the finding rejected, deferred, or blocking when the evidence does not support a safe change.

Do not target a preferred number of tasks. Prefer the smallest graph whose nodes and edges remain independently justified.

## Required invariants

A revised plan must preserve:

- the intent identifier and statement unless the user approved an intent change;
- every success-evidence item, constraint, and non-goal;
- complete primary requirement coverage;
- executable acceptance and evidence contracts;
- real dependency and audit closure;
- compatibility, risk, rollback, monitoring, and inspection obligations;
- valid completed work and evidence in a canonical replan;
- the current demonstrable baseline, justified increment ladder, and historical gate evidence;
- explicit uncertainty and rejected alternatives needed for future reasoning.

After refinement, run graph validation and the requirement/claim trace above; inspect parallel readiness and brownfield assurance when applicable. Revisit deeper pathfinder analysis only for changed paths or unresolved load-bearing uncertainty. A structurally valid graph can still fail this semantic review.

## Review artifact

Write `pyramid-plan-review-v1` JSON against `../schemas/plan-review.schema.json`. Bind it to the source and revised plan hashes. Record facts separately from findings, connect findings to fact IDs, trace each intent requirement before and after, state invariant results, report graph metrics, and name limitations. A review may validly conclude `retained` when every apparent simplification would weaken the contract.

For these review references, compute SHA-256 over the exact saved plan file bytes, as in the published example; do not substitute a reserialized JSON hash or runtime mutation guard. A retained candidate has identical source/revised hashes. Recompute the binding after any file change.
