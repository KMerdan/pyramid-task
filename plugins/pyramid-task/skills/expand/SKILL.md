---
name: expand
description: Propose and apply a deeper subtree for a broad executable Pyramid Task V3 node while preserving its purpose, stable ID, dependencies, evidence contract, assurance provenance, and history. Use only when Codex detects multiple independently reviewable work units, mixed work modes, unsafe scope, or a composition boundary needing explicit children and a joint audit; obtain user clarification and approval before changing topology.
---

# Expand a Pyramid Task

Read `../../references/expansion-contract.md`, `../../references/graph-contract.md`, `../../references/agent-contracts.md`, `../../references/brownfield-assurance.md`, and `../../references/lifecycle-contract.md` completely before proposing expansion. Use `../../assets/example-expansion.json` as a structural example only.

## Decide whether to propose

Inspect the task contract and nearby graph. Propose expansion only when evidence shows at least one material signal:

- two or more independently reviewable deliverables;
- research, decision, contract, implementation, or integration work mixed in one task;
- work that cannot safely fit one agent cycle or write scope;
- acceptance evidence that needs distinct owners or checks;
- parallel branches whose composition needs a joint audit;
- a blocker caused by the task being too broad.

Continue the original task without asking about expansion when none applies. Difficulty, file count, or task length alone is not sufficient.

## Propose, clarify, and preview

1. Release an active claim before expanding. Reopen implemented or verified work first. Do not expand an audit node.
2. Preserve the current task ID and complete contract in `preserved_parent`. Draft at least two executable child branches and exactly one audit gate at the next level.
3. Map every current dependency to the children that consume it. Make the audit gate cover every branch. Record evidence, trigger signals, impact, and resolved user decisions in `expansion-proposal-v1` JSON.
4. Lead with a concrete recommended subtree and its impact. Ask only questions that materially change scope, ownership, ordering, or acceptance evidence; ask at most three at once and include recommended defaults.
5. If clarification changes the original purpose, acceptance contract, architecture, selected path, or surrounding topology, stop and use `replan` instead.
6. Preview the exact graph diff:

```bash
python3 ../../scripts/pyramid.py expand --project <project-root> --proposal <expansion.json> --actor <actor> --preview --json
```

7. Show the preserved parent, added children, dependency mapping, joint gate, risks, graph version, and proposal hash. Request explicit approval to apply this exact proposal.

## Apply only after approval

Record the approving user and a durable conversation or task reference:

```bash
python3 ../../scripts/pyramid.py expand --project <project-root> --proposal <expansion.json> --actor <actor> --approved-by <user> --approval-reference <reference> --approved-proposal-sha256 <preview-hash> --apply --json
```

Report the new ready frontier, invalidated proofs and inspections, assurance gaps for new child tasks, and audit path. A child may later be expanded through the same workflow, creating arbitrary depth one reviewed level at a time. Re-run `pyramid-task:impact` before brownfield child audits.

## Boundaries

- Let the agent discover expansion; let the user own the topology change.
- Never apply before an explicit approval that follows the preview.
- Never use expansion to change the original contract or selected path.
- Never invent approval metadata or treat silence as approval.
- Never hand-edit plan, state, events, or generated projections.
