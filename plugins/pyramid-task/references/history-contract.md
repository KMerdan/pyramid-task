# Intent Chronicle Contract

Pyramid keeps the active intent graph small and stores cross-intent implementation history in a separate append-only ledger. The ledger explains why the system changed, how the work progressed, which evidence justified it, and how closely an authorized agent can reproduce the result.

## Storage model

```text
.pyramid/history/
├── head.json
├── index.json
├── transaction.json  # present only while an append needs completion
└── records/
    ├── START-....json
    ├── CHRONICLE-....json
    └── BINDING-....json
```

- `pyramid-intent-start-v1` records the intent, starting plan, source snapshot, runtime identity, and parent chronicle at intent creation.
- `pyramid-intent-chronicle-v1` records a completed or deliberately archived intent. It contains the ending plan, outcome path, decision and event references, task-to-file evidence bindings, provenance gaps, replay commands, reports, and a human narrative.
- `pyramid-code-binding-v1` binds an existing chronicle to a later clean Git commit without rewriting that chronicle.
- `pyramid-history-head-v1` seals record order and content hashes as an append-only chain.
- `pyramid-history-index-v1` is a disposable query projection. Rebuild it; never treat it as canonical truth.
- `pyramid-history-transaction-v1` is a recoverable prepared append. The runtime writes it before the immutable record and head, then removes it only after the index is rebuilt and the committed ledger validates.

The active `plan.json`, `state.json`, and per-plan events remain authoritative for current execution. History does not add a node type, lifecycle state, wave, or completion claim.

## Lifecycle behavior

- `create` and `reset` capture an intent-start record. Historical migration events remain preserved; no new migration is performed.
- `close` appends a completed chronicle after the final report, optional change dossier, and `plan.completed` event exist.
- Archiving active work appends an `archived-incomplete` chronicle. Archiving a completed intent reuses its completed chronicle.
- `reset` and `restore` preserve the project-wide ledger. A reset candidate may not reuse a historical `plan_id`; restore the matching archive instead.
- Reopening and reclosing an intent appends another chronicle cycle linked to the prior one. It does not rewrite the earlier completion claim.
- Archives include the history known when the snapshot was frozen, while restore preserves any newer project-wide records.

## Provenance and replay strength

Task result `changed_files`, checks, and acceptance evidence provide the causal binding from implementation work to code. The chronicle compares those declarations with Git changes when a start snapshot is available and reports `complete`, `partial`, or `unavailable` coverage. Missing bindings remain visible; the runtime does not infer them from filenames.

Replay fidelity is calibrated:

- `artifact-identical`: a later clean Git commit descends from the recorded start and its material commit range exactly matches declared task changes;
- `behaviorally-equivalent`: task evidence and validation commands are complete, but no distinct clean end commit is bound;
- `partial`: source identity, provenance, commands, or environment evidence is incomplete.

A code binding is a separate immutable record because closure commonly precedes the final repository commit. Bind only after the implementation is committed and the worktree is clean:

```bash
python3 ../../scripts/pyramid.py history --project <project-root> --bind <chronicle-or-plan-id> --actor <actor> --json
```

The runtime rejects binding when the end commit does not descend from the recorded start, committed material files are unbound, declared files are absent from the commit range, or the worktree is dirty.

Chronicle summaries expose code-binding readiness independently from replay fidelity:

- `established`: an exact clean commit range is already recorded;
- `pending`: a completed intent has a usable start commit and can be bound after its implementation is committed cleanly;
- `unavailable`: no start commit exists, so exact code binding cannot be reconstructed;
- `optional`: an incomplete archive may be bound only when exact reproduction is worth preserving.

Starting another intent does not silently block on a missing binding, but its preview carries the binding warning inside the approval hash.

## Queries

Use the smallest bounded query:

```bash
python3 ../../scripts/pyramid.py history --project <project-root> --json
python3 ../../scripts/pyramid.py history --project <project-root> --intent <plan-or-chronicle-id> --json
python3 ../../scripts/pyramid.py history --project <project-root> --path <repository-path> --json
python3 ../../scripts/pyramid.py history --project <project-root> --commit <git-commit> --json
python3 ../../scripts/pyramid.py history --project <project-root> --replay <plan-or-chronicle-id> --json
python3 ../../scripts/pyramid.py history --project <project-root> --doctor --json
```

The replay query is read-only. It returns starting and ending plans, change bindings, recorded validation commands, limitations, and an execution policy. Running commands, checking out commits, creating worktrees, or changing external state still requires normal task authority.

## Human interpretation

The History Observer reads only the compact history summary generated from canonical chronicles. For each intent it shows:

- why the work began;
- the demonstrated outcome path;
- failures, replans, or other turning points;
- why the intent ended in its recorded state;
- declared changed-file coverage;
- replay fidelity and bound commit.

Do not present the ledger as a changelog alone. A human should be able to follow cause, progress, evidence, and final rationale without reading machine IDs or raw event payloads.

## Recovery

Normal reads stop when `transaction.json` is present so observers never combine an old head with a new record. Diagnose the prepared append first:

```bash
python3 ../../scripts/pyramid.py history --project <project-root> --doctor --json
```

With explicit recovery authority, complete it deterministically:

```bash
python3 ../../scripts/pyramid.py history --project <project-root> --repair --json
```

Repair never invents a record. It verifies the prepared payload, predecessor, intended head, semantic links, file hash, and committed ledger, then rebuilds the disposable index. Divergence or malformed content remains blocked for manual investigation.

## Integrity boundaries

- Never edit or delete a history record to correct it. Append a new closure cycle or binding.
- Never claim missing evidence from Git inference alone.
- Never promote replay fidelity because commands look plausible; use the recorded coverage and binding result.
- Never mix old intent nodes into the current ready frontier.
- Never execute a replay preview automatically.
- Treat the hash chain as tamper-evident relative to a trusted `head.json`, not as an external signature or independent timestamp.
- Review chronicles before sharing them: plans, file paths, recorded commands, and runtime metadata may be repository-sensitive.
