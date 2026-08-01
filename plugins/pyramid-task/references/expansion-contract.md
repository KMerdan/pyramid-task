# Expansion Contract

Expansion adds internal detail without changing the task's meaning. The agent owns discovery and recommendation; the user owns the topology change.

## Expansion versus replan

Use `expand` only when the target purpose, acceptance criteria, required evidence, selected mechanism, parent relations, and external consumers remain valid. Preserve the task ID so upstream and downstream references remain stable.

Use `replan` when clarification changes the goal, contract, architecture, selected path, or topology outside the target. Do not hide a replan inside an expansion proposal.

## Eligible target

The target must be a primary non-audit executable node in an active plan. It must be unclaimed and have execution `planned` or `needs-rework`. Release a working claim first. Reopen implemented or verified work before proposing expansion.

The target must not already have contributing children. Replan an existing subtree instead of grafting another hierarchy onto it.

## Proposal contract

Create `expansion-proposal-v1` against the current `base_graph_version`. Follow `../schemas/expansion-proposal.schema.json` and preserve the current node fields byte-for-structure in `preserved_parent`.

The proposal contains:

- a reason, concrete trigger signals, and evidence references;
- at least two primary executable work branches at `parent.level + 1`;
- exactly one primary audit node at the same level;
- explicit joint-gate coverage for every non-gate branch;
- internal typed dependencies;
- a complete mapping from every current target dependency to one or more child consumers;
- resolved user decisions and scope, risk, and execution-order impact.

Every child contributes directly to the stable parent. The parent becomes non-executable kind `work-package`. Existing edges incident to the parent remain unchanged. The runtime adds `validated-by` from the parent to the new audit gate and makes the gate depend on every child.

## Approval protocol

Always preview first. The preview validates the proposed graph and returns the exact diff, graph version, and canonical proposal SHA-256. Present those effects before requesting approval.

Apply only after explicit user approval. Supply `approved_by`, a durable `approval_reference`, and the exact `proposal_sha256` returned by preview. The runtime rejects missing approval metadata, a changed proposal hash, stale graph versions, changed parent contracts, invalid dependency mappings, uncovered branches, cycles, and ID collisions.

The immutable `task.expanded` event records the complete proposal, hash, approval provenance, diff, and invalidated proofs. Approval does not expand normal filesystem, service, deployment, messaging, or destructive-action authority.

## State and audit semantics

On application, the parent becomes an unverified work-package. New children start planned. Previously valid downstream proofs become stale and at-risk, while historical results remain in state and events.

The work-package is not executable. Its audit can pass only after its contributing children and joint gate pass. External consumers still depend on the stable parent, so they cannot treat individual child completion as proof of the original task contract.

Expansion is recursive. Expand a child only through a new current-version proposal and a new user approval. Each operation adds one level, keeping deep graphs reviewable and auditable.
