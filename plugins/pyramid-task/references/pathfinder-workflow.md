# Evidence-Based Pathfinder Workflow

Use this workflow for creation and replanning. The goal is not to maximize task count; it is to establish a defensible route from the observed current state to a testable intended state.

## 1. Normalize the intent

Record:

- actor or beneficiary;
- current state;
- desired final state;
- observable success evidence;
- invariants and constraints;
- non-goals;
- facts, assumptions, and unresolved questions.

Classify ambiguity as blocking, assumption-worthy, or locally decidable. Ask about blocking ambiguity. Record other assumptions with confidence and a validation node when the assumption is load-bearing.

## 2. Gather evidence

Inspect the repository, tests, schemas, architecture, existing plans, and relevant authoritative sources. Give each evidence item a stable ID, claim, source, confidence, freshness note, and supported nodes. Record contradictions instead of averaging them away.

Stop research when every critical edge is supported, explicitly assumed with an early validation node, or identified as blocking. More sources are not a substitute for resolving a load-bearing contradiction.

## 3. Construct the pathfinder

Backward-chain from the final intent by asking what must be true immediately before it. Repeat until reaching implementable or researchable conditions.

Forward-chain from the repository's current state by asking what can be built and meaningfully tested now. Reject backward paths that cannot connect to the forward chain.

Use outcome nodes for required states. Use executable nodes for actions that establish or test those states. Use joint audit nodes to test whether sibling branches compose.

## 4. Compare paths

Compare material alternatives on:

- evidence strength;
- constraint fit;
- risk and failure containment;
- reversibility;
- dependency burden;
- testability;
- migration and compatibility cost.

Mark one path primary. Keep alternatives when they are plausible fallbacks. Mark a rejected path with the decision and evidence that rejected it.

## 5. Convert to a pyramid

Set level as distance from the intent: the intent is level 0 and implementation detail increases downward. Set wave as the earliest safe execution sequence; do not confuse wave with level.

Convert shared prerequisites to foundation tasks, uncertain edges to research tasks, contracts to contract tasks, branch composition to integration and audit tasks, and final success evidence to the intent audit.

## 6. Audit the plan

Before creation or replan, check:

- every primary node traces to the intent;
- every intent criterion has an implementation and evidence path;
- every executable node is bounded and independently reviewable;
- broad executable nodes are left intact unless evidence justifies an approved expansion;
- every multi-branch composition has an audit gate;
- every critical assumption has an early validation task;
- dependencies are typed and minimal;
- no hard dependency or hierarchy cycle exists;
- alternative and rejected paths cannot enter the ready frontier.

## 7. Repair failures

When an audit fails, the runtime moves the affected executable claim to `needs-rework` and invalidates dependent proofs. Preserve still-valid implementation and evidence. Repair locally when the mechanism remains valid; replan when a load-bearing assumption, contract, or selected path is invalid. Never lower the original success criterion merely to make the graph complete.
