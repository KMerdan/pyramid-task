# Demonstrable Increment Contract

Begin planning from a ladder of usable, testable states rather than from a list of implementation activities. A **demonstrable increment** is the smallest honest project state that an intended actor can use, exercise, inspect, or decide from. For software, prefer a **runnable increment**: the product builds or starts and a meaningful scenario succeeds.

This is a planning and audit convention over the existing graph contract. It adds no node kind, execution state, or serialized field.

## Terms

- **Current demonstrable baseline**: the latest observed state that can be exercised now, including an honestly recorded non-runnable starting state.
- **Increment ladder**: the ordered states between that baseline and the final intent.
- **Increment outcome**: one primary `outcome` node describing a rung in the ladder.
- **Increment gate**: one primary `audit` node connected from its outcome with `validated-by` and backed by reproducible evidence. The rung is accepted when the gate and then its outcome pass audit.
- **Inherited proof**: prior increment scenarios that a later gate must repeat or otherwise establish against the current candidate.

`level`, `wave`, and parallel groups keep their existing meanings. A level is distance from the intent. A wave is earliest safe execution time. A parallel group is a disposable conflict-safe scheduling result. None proves a demonstrable increment.

## When to define the ladder

During create or new-intent, define the current demonstrable baseline and candidate ladder immediately after normalizing the intent and gathering enough evidence to avoid fictional slices. During replan, preserve verified rungs and revise only the affected current or future portion.

Prefer the smallest sequence in which every rung has distinct actor-visible value or risk-reducing proof. A valid plan may have one increment when no smaller honest state exists. Do not manufacture demos, split one inseparable behavior, or call setup alone an increment.

Use domain-appropriate proof:

- application or game: build or launch plus a meaningful user scenario;
- API or service: start, health check, and one real request path;
- library: install or import, executable example, and public-contract tests;
- infrastructure: apply in a bounded environment, observe health, and prove rollback;
- data workflow: run against a representative fixture and verify material outputs;
- research or design: produce evidence or a prototype that resolves a stated decision and changes what work can safely follow;
- documentation: render the artifact and exercise the user journey it supports.

## Represent the ladder with the current graph

1. Record the current demonstrable baseline, ordered ladder, and rejected slicing alternatives in a selected-path `decision`, supported by plan evidence or the brownfield baseline.
2. Represent each rung as a primary `outcome`. State the actor-visible capability in its summary, acceptance criteria, and required evidence; do not rely on the word “increment” in its title as proof.
3. Prefer a cumulative outcome chain: the earlier increment outcome contributes to the next increment outcome, and the final increment outcome contributes to the intent. Attach the implementation, integration, research, contract, and risk-control work that newly establishes each rung with `contributes-to` edges. Shared foundations contribute to the earliest rung that consumes them.
4. Give every increment outcome its own primary audit node. The outcome points to that node with `validated-by`; the gate depends on all work and evidence needed to exercise the rung.
5. Order acceptance, not necessarily implementation: each later increment gate has a `validation-requires` dependency on the previous increment outcome. That outcome cannot pass until its own gate passes. Work may start ahead when ordinary graph dependencies and conflict analysis permit it, but a later rung cannot pass first.
6. Make every later gate re-establish the observable proofs inherited from earlier rungs against the current candidate. A historical pass proves what was accepted then; it is not current regression evidence after later changes.
7. Audit the intent after the final increment outcome passes. Add a distinct final intent gate only when the intent has additional direct branches or release-level composition evidence not established by the last increment. When multiple increment outcomes instead remain direct siblings of the intent, its separate final gate must cover every increment outcome. Do not reuse an increment gate in a way that makes an outcome depend on its own verification.

In the cumulative chain, earlier increments sit at greater `level` values because they are farther from the intent; do not place every rung at level 1. Waves remain chronological scheduling facts and may increase in the opposite visual direction.

The normal runtime still derives readiness from typed edges and state. Skills must not invent a separate increment status or hand-edit canonical state.

## Design each gate

An increment gate should normally establish:

1. **Constructability** — the artifact builds, installs, deploys, renders, or otherwise becomes available.
2. **Entry** — the intended actor can start or access it through a documented path.
3. **Meaningful scenario** — at least one end-to-end behavior or decision promised by this rung succeeds.
4. **Inherited behavior** — prior accepted scenarios still succeed against the current candidate.
5. **Safety and recovery** — applicable compatibility, rollback, monitoring, inspection, and material-finding obligations are satisfied.
6. **Reproduction** — commands, fixtures, environment assumptions, and evidence locations let another agent repeat the proof.

Use the smallest proof that is representative. A process starting and exiting successfully is insufficient when the increment promises usable behavior. Manual evidence is acceptable only when automation is unreasonable and the observation is specific and reproducible.

Exercise the actual public entry point and critical integration boundaries early in the increment, before broad qualification. For an agent application this includes the prompt/tool/result path visible to the real parent agent, not only internal service tests. Keep final cumulative acceptance and disclose simulated providers or effects.

The first gate must demonstrate the smallest complete promised public journey.
Harness installation or a component matrix is supporting work, not that journey.
Add only missing observation capability needed by the outcome; put its dependency
at the acceptance that consumes it. Independent product work need not wait for a
VM, browser, release credential or optional integration it does not consume.

Name the delivery environment in the evidence contract. Record candidate source/build identity and distinguish candidate verification from demonstrated availability in the intended installation. A user-equivalent isolated installation does not prove the user's running process was updated; deployment still requires its normal authorization. Express this in existing acceptance/evidence records, not new execution states.

## Shape work around increments

- Decompose vertically through the layers needed to demonstrate a rung. Avoid horizontal “all backend, then all UI, then test” paths when a thinner end-to-end slice is feasible.
- Give each executable task a bounded behavior and identify its likely entry points and integration owners. Avoid broad behavioral promises paired with arbitrary tiny file lists; stop mapping when the task's acceptance and ownership boundaries are clear.
- Trace every primary executable node to the earliest increment it establishes, validates, or safely enables. Research may support a later rung without pretending to be runnable value.
- Keep waves truthful. One increment may require several waves, and one wave may contain safe work for different future increments.
- Treat task `implemented` and batch completion as intermediate facts. Only the increment gate and outcome audit establish the rung.
- End a delivery cycle only after the increment gate and its outcome pass audit, not at an arbitrary wave boundary.

## Refine, replan, and expand

Simplification may merge adjacent rungs only when their separate actor value, risk boundary, acceptance evidence, and recovery boundary were not real. It should remove ceremonial gates and restore missing vertical slices, but never optimize for a preferred number of increments.

Replan from the earliest invalid rung. Preserve historical passes and unaffected evidence, mark replaced paths `superseded`, and update inherited checks for every later candidate rung. Do not weaken a failed gate merely to retain the schedule.

Expansion preserves the enclosing increment contract. Its internal joint gate proves that the expanded work composes; it does not replace the increment gate unless it independently exercises the complete increment outcome.

## Report progress

When a human asks about delivery progress, report:

- the last verified demonstrable increment and the evidence date or context;
- the next increment outcome, its gate, and exact blockers;
- work occurring ahead of that gate separately;
- stale or failed inherited proof;
- the remaining rungs to the intent.

Never call a wave, ready frontier, implemented task set, or attractive visualization a runnable release.
