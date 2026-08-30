---
name: history
description: Inspect and explain Pyramid Task V3 intent chronicles across implementation cycles, trace a repository path or Git commit to why and how it changed, produce a bounded read-only replay context, diagnose or recover an interrupted ledger append, or bind a closed intent to a clean descendant Git commit. Use when a human needs the causal project story or an agent needs reproducibility evidence beyond the active intent graph.
---

# Inspect Pyramid Intent History

Read `../../references/history-contract.md`. Load `../../references/lifecycle-contract.md` only for archive, reset, restore, reopen, or close semantics; load `../../references/agent-contracts.md` only when diagnosing incomplete task-to-file bindings.

## Workflow

1. Validate the project. If validation reports a pending history append, inspect it without mutation:

```bash
python3 ../../scripts/pyramid.py history --project <project-root> --doctor --json
```

Run `history --repair` only when the user asked to recover the ledger. It may complete the exact prepared append, but it must reject malformed or divergent state.
2. Use the smallest read-only query:

```bash
python3 ../../scripts/pyramid.py history --project <project-root> --json
python3 ../../scripts/pyramid.py history --project <project-root> --intent <plan-or-chronicle-id> --json
python3 ../../scripts/pyramid.py history --project <project-root> --path <repository-path> --json
python3 ../../scripts/pyramid.py history --project <project-root> --commit <git-commit> --json
python3 ../../scripts/pyramid.py history --project <project-root> --replay <plan-or-chronicle-id> --json
```

3. For a human explanation, lead with why the intent began, its demonstrated path, turning points, why it ended as recorded, and the evidence or limitations behind that account.
4. For agent continuation or reproduction, return the replay fidelity, start and bound commits, starting and ending plans, task-to-file bindings, recorded checks, and every limitation. Treat the replay result as context, not permission to execute.
5. After the implementation is committed, bind the chronicle only when the user asks to establish commit provenance and the worktree is clean:

```bash
python3 ../../scripts/pyramid.py history --project <project-root> --bind <chronicle-or-plan-id> --actor <actor> --json
```

6. Report rejected bindings as provenance gaps. Do not weaken the check or rewrite the chronicle.

## Boundaries

- Keep the active graph and ready frontier scoped to the current intent.
- Never hand-edit `.pyramid/history`, infer missing changed files, or promote replay fidelity from prose.
- Never delete `transaction.json` to bypass recovery. Use `--doctor`; use `--repair` only to finish the validated prepared record.
- Never execute replay commands, check out commits, or create worktrees during a history inspection.
- Distinguish an exact repository-tree binding from deterministic runtime behavior; surface environment limitations.
