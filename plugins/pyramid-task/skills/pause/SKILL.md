---
name: pause
description: Pause a currently claimed Pyramid Task V3 executable node with a complete, durable, evidence-aware handoff. Use when an agent must stop implementation for a break, context window, shift, or safe transfer without releasing the work informally or losing exact continuation context.
---

# Pause a Pyramid Task

Read `../../references/handoff-contract.md`. Load `../../references/agent-contracts.md` only for ownership or transition edge cases, `../../references/brownfield-assurance.md` only when the task packet contains assurance context, and `../../references/lifecycle-contract.md` only if the runtime rejects the plan state.

## Workflow

1. Confirm the task is currently `working`, the actor owns it, and its packet is current. Reuse `mutation_guards.task` for the pause guard. Do not pause another actor’s work.
2. Capture the real continuation state before stopping: completed and unfinished work, every changed file and affected asset, commands and their actual results, decisions and assumptions, blockers, risks, exact next steps, required context, external session references, and any running resource that needs attention.
3. Create `pyramid-handoff-draft-v1` JSON. Start from `../../assets/example-handoff-draft.json`; never invent a passed check or hide a changed file.
4. Choose the pause mode deliberately:
   - `hold` is for a short break. It retains the actor’s exclusive ownership until `--resume-minutes` expires.
   - `handoff` releases ownership immediately so another actor can resume from the same evidence record.
5. Pause through the runtime. The runtime adds plan identity, graph version, assurance and worktree fingerprints, writes immutable JSON and Markdown handoff records, changes only this task to `paused`, and emits `task.paused`.

```bash
python3 ../../scripts/pyramid.py pause \
  --project <project-root> --node TASK-203 --actor <actor> \
  --reason "Coffee break after the validation seam" \
  --handoff /path/to/handoff-draft.json \
  --mode hold --resume-minutes 60 \
  --expected-guard <task-guard> --json
```

6. Report the handoff ID, pause mode, deadline (if any), and its exact resume command. The task is not released, implemented, verified, or archived by pausing it.

## Boundaries

- Do not use `archive`, `reset`, or `release` for a temporary break.
- Do not hand-edit `.pyramid/state.json`, events, or generated handoff records.
- Do not pause with a partial one-line note; use the full draft contract even for a short break.
- Do not pause an expired lease. Inspect and reclaim or resolve ownership first.
- A pause is task-level: it must not stop independent ready work in the same graph.
