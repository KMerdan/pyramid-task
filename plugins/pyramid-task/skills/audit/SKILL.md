---
name: audit
description: Audit a Pyramid Task V2 implementation node, joint gate, level outcome, or final intent against explicit evidence. Use when Codex must determine whether completed work is correct, whether branches compose, or whether a parent claim may become verified.
---

# Audit a Pyramid Task

Read `../../references/agent-contracts.md`, `../../references/graph-contract.md`, and `../../references/lifecycle-contract.md` completely before auditing.

## Workflow

1. Inspect the target node, its acceptance criteria, required evidence, dependencies, children, and validation gate.
2. Execute or inspect every required check. Seek disconfirming evidence for load-bearing claims and composition edges.
3. Create an `audit-result-v1` JSON file with per-check results and evidence references.
4. Submit the result:

```bash
python3 ../../scripts/pyramid.py audit --project <project-root> --node GATE-205 --actor <actor> --result pass --evidence <audit-result.json> --json
python3 ../../scripts/pyramid.py audit --project <project-root> --node GATE-205 --actor <actor> --result fail --evidence <audit-result.json> --json
```

5. On failure, identify affected claims and recommend repair or replan. The runtime moves an executable failure to `needs-rework` and invalidates stale dependent proofs. Do not silently weaken the acceptance criterion.
6. Verify a parent outcome only after required children and its joint gate are verified.
7. After the final intent passes, inspect lifecycle. Run `close` when `closure_ready` is true so the verified intent receives a final report and formal completed state.

## Boundaries

- Never pass an audit from task status alone.
- Never use missing evidence as positive evidence.
- Prefer an independent auditor for critical joint and intent gates.
- A failed audit must remain visible in state and history until repaired or superseded.
