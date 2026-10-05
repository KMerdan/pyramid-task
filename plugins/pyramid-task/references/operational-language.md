# Operational language

This is a small original STE-inspired profile, not ASD-STE100 compliance or a
dictionary. Consult it only when authoring guidance or resolving ambiguous terms;
do not load it with every packet or cosmetically reword an active canonical plan.

| Term | Decision it supports |
| --- | --- |
| Authorized | The human/host permits this exact effect and scope; plan readiness cannot grant it. |
| Reviewed | A named reviewer inspected named inputs and reported findings/limits; not necessarily tested or accepted. |
| Task-ready | The runtime permits starting this node; it does not prove the outcome. |
| Audit-ready | Current prerequisites, proof and assurance permit attempting this audit. |
| Implemented | The worker submitted scoped work; verification is pending. |
| Verified | The claim passed its audit; current source/proof eligibility must still be checked before reuse. |
| Blocked | A named requirement prevents a named action; independent authorized work may remain possible. |

Use condition → actor → action → limit for consequential instructions. Prefer one
principal action per sentence. Use MUST/MUST NOT for real invariants, SHOULD for
defaults and MAY for options; these words never override host permissions.

## Decision triggers

| Condition | Agent action and stopping limit |
| --- | --- |
| Established project; ordinary status question | Use the smallest native query. Stop relying on a failed validation result. |
| First trust, recovery, suspected corruption or final acceptance | Run complete `validate`; do not substitute a narrow read for full-chain integrity. |
| Current claimed task; health-only report | Reuse the packet/guard; no new harness or test solely for health. |
| New check required | Capture inputs before execution; never recapture afterward to disguise change. |
| Existing proof proposed for reuse | Check claim, contract, inputs, environment and artifacts; rerun only affected invalid proof. |
| Guard conflict | Inspect the affected node and reconcile facts before retrying; never silently renew authority. |
| Missing/new authority or uncertain ownership/isolation | Stop the affected operation and request the exact missing decision; continue independent authorized work. |

Mandatory skill reads, host restrictions and explicit project checks remain
mandatory. Reuse supporting context only while relevant facts remain current.

Keep observed result, evidence reference and limitation separate. A model claim,
hash, file, process start or simulated effect is not execution or visual proof.
Do not label an unknown/failed/missing check passed. Required human decisions
cover new authority, material intent changes, irreversible/high-impact effects
and unresolved consequential risk—not routine automated or model review.

Recheck unchanged policy only when relevant facts change or the user requests it.
Use the current task's relevant reference sections; missing context is a reason
to inspect that context, not preload every workflow. Reuse current proof only when
it establishes the actual claim and its inputs/environment/artifacts still match.
