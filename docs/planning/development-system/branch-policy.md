# Release and development boundary

Owner decision: 2026-10-06. Target: Standalone Pyramid Skill only.

| Branch | Role | Local checkout |
| --- | --- | --- |
| `main` | Formal 4.1 release; tracked tree restored to `58559af` | `/Users/merdankiji/localGit/pyramid-task` |
| `dev/improvement` | 4.2 development, new Intent r3 and subsequent improvements | `/Users/merdankiji/localGit/pyramid-task-improvement` |

Complete the required development and gates on `dev/improvement`. Merge to
`main` only after the owner authorizes release integration. A development push
does not authorize a release, installation or canonical intent activation.

## Correction and future integration

The earlier push incorrectly published `2fa2e83` (4.2 source) and `e831b02`
(Intent r3 records) on `main`. Ordinary reverts `17a1cba` and `61a42f5` restore
the exact 4.1 tracked tree. No force-push or published-history rewrite is used.
The original commits and planning records remain recoverable on the development
branch and in Git history.

Development checkpoint `5160c45` records that rollback as a merge parent while
retaining the complete `e831b02` tracked tree. This explicitly keeps the 4.2
delta on the development side of the restored release baseline; a later merge
must not silently omit it because the original commits were reverted on main.
This is a main-to-development integration checkpoint, not a development release.

## Uncommitted work and evidence

The 15 Observer source/document files previously pending in the main checkout
were restored byte-for-byte in the development worktree. They remain uncommitted;
this administrative correction does not claim their acceptance or include them
in its documentation commit. Recoverable stash
`66f33889bf86d819877e8e73c3e050716fa4a353` remains intact.

The original `.pyramid` and `proof-output/observer/` stay in the main checkout,
where the completed Observer history was recorded. The development checkout's
separate `.pyramid` also stays unchanged. Source relocation does not transfer
canonical authority, requalify proof, or bind a new intent. Do not blindly copy
state between worktrees or load all historical captures as context.

Stored transition previews, readiness and planning-validation reports describe
their original checkout/time. Reinspect the development worktree and preview
the next intent there before activation; do not reuse the old main preview hash.
The planning checker resolves source relative to this repository, not by a
hard-coded main path. Installed controllers remain separate and unchanged.
