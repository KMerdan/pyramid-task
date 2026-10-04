# Native host decision and usage pilot — 4.1 candidate

Date: 2026-10-04. Actual serial native CLI sessions, not simulated agents.
The final package manifest is [package-identity.json](../TASK-432/package-identity.json).
Base source: 3d787c5c2038d61f1146f24ba20188bfd18b6495; no 4.1 commit exists.
The baseline/candidate inputs were identical copies of cases/facts.md and request.md.
The evaluator rubric was withheld from the hosts.

## Observed decisions

| Case | Codex 4.0 | Codex final 4.1 | Claude 4.0 | Claude final 4.1 |
| --- | --- | --- | --- | --- |
| EXTENSION | Correct consumer-coupled 4.0 limit | Correct explicit legacy binding and separate composition | Incorrect assumption that unchanged 4.0 proof remains current | Correct conditional binding; runtime-code identity left unknown |
| GUARD | Safe, but also suggests replacing the literal | Invocation argument/environment; old helper review stale | Correct invocation data and affected review | Correct invocation data and affected review |
| BLOCKER | Preserve denied VM; scoped replan and independent work | Same, smallest public journey and necessary capture | Same boundaries and public journey | Same boundaries; replan approval retained |
| REVIEW | Reuse unchanged policy review; refuse unapproved production deletion | Same | Same | Same |
| PROOF | Current database proof only; simulated mail not real delivery | Same | Same | Same |
| VISUAL | Unviewed capture is not usability proof | Same; existing capture may suffice if actually viewable/current | Same | Same |

All final next actions preserve authority, relevant freshness and missing visual
acceptance. No critical false-evidence acceptance or forbidden mutation occurred.
No human question was actually asked by either pilot. Replan approval in the
recommendations remains the existing guarded boundary, not measured proof that a
host will never ask an unnecessary question. Claude's final runtime-source unknown
is retained, not scored as fully resolved; actual native plugin metadata, source
manifest and separate real runtime checks establish the selected package.

## Actual operations and affordances

Codex 0.155.1: repository-local .agents/skills/inspect/SKILL.md, --ignore-user-config,
--ephemeral, read-only sandbox, never approval, native default model (actual model
identifier not exposed), no helper/remote/product/browser tool. Baseline six shell
calls; final eight. The final source search had one harmless unmatched-glob exit 1,
then a narrower search succeeded. No mutations.

Claude 2.1.286: session-only --plugin-dir ./package, restricted Read/Glob/Grep/Bash/Skill,
dontAsk/permission-prompts none, empty user setting sources, hooks/memory disabled,
strict empty MCP config, no Chrome/session persistence. Actual native model:
claude-opus-5-5. Both matched baseline/final sessions used eleven tool calls, one
Bash probe, with no permission denial or mutation. Both hosts actually ran the
owned fixture's ready probe: graph 1, RESEARCH-101 planned/unverified, clear,
unowned, no blockers. This was not task acceptance or case-product execution.
Separate fixture validation/harness queries were not performed by these pilots.

Normal configured authentication stayed with the CLIs. No credentials, private
history or installed plugin files were copied or changed. User explicitly approved
source/instruction and sanitized fixture transfer to the two providers.

## Exposed aggregate usage

| Native counter | Codex baseline | Codex final | Claude baseline | Claude final |
| --- | ---: | ---: | ---: | ---: |
| input_tokens | 137298 | 172607 | 12 | 12 |
| cached_input_tokens / cache_read_input_tokens | 105344 | 144512 | 96197 | 98937 |
| cache_write_input_tokens / cache_creation_input_tokens | 0 | 0 | 18849 | 21971 |
| output_tokens | 1823 | 1762 | 4431 | 4290 |
| reasoning_output_tokens / thinking_tokens | 111 | 35 | 467 | 322 |

These are native aggregate counters across iterative calls, not context-window
occupancy. Reasoning/thinking are separately exposed components; do not add them
again to output totals. Cache accounting differs by host. Codex model identity
is unknown, despite matching requested CLI defaults. Claude's native list-price
cost estimates are not subscription charges. No cross-host cost comparison,
general token savings, latency gain, end-to-end productivity or reliability claim
is supported. Aggregate candidate input accounting increased on both hosts.

## Failed/discordant attempts and limits

The initial Claude candidate appended echo/ls to the allowed probe. The host
denied it; Claude did not retry or claim a result. Its full final decision and
denial remain in claude-candidate-initial-blocked-trace.json. Baseline and corrected
candidate then used the exact same allowed command with permissions unchanged.

The unrepaired Claude candidate did not establish exact compatibility. A narrow
TASK-432 scope amendment added the existing harness reference, documenting the
tested rule without changing runtime/acceptance. Both final candidate sessions
were run against the repaired frozen package; earlier runs remain historical.

Traces are mechanically sanitized: account/session metadata excluded, large tool
outputs explicitly truncated with original length/hash. Final decisions and
usage remain complete. Selected packaged file hashes are in the source manifest;
original owned logs remain in temporary staging, not normal agent packets.

Case VM/database/mail/browser facts are supplied fixtures, not real external
observations. One matched six-case batch per host is a small decision pilot, not
a statistical benchmark or install qualification. Runtime subprocess proof and
independent final join review are separate obligations.
