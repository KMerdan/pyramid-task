---
name: audit
description: Audit a Pyramid Task V3 implementation node, joint gate, level outcome, or final intent against explicit evidence and brownfield inspection coverage. Use when the agent must determine whether completed work is correct, whether branches compose, whether predicted impact matches actual scope, or whether a parent claim may become verified.
---

# Audit a Pyramid Task

Read `../../references/agent-contracts.md`, `../../references/graph-contract.md`, `../../references/brownfield-assurance.md`, and `../../references/lifecycle-contract.md` completely before auditing.

## Workflow

1. Inspect the target node, its acceptance criteria, required evidence, dependencies, children, and validation gate.
2. In brownfield mode, inspect canonical impact, inspection, finding, drift, rollback, monitoring, and legacy-bridge records. Compare predicted scope with the worker's actual changed files and assets.
3. Execute or inspect every required check. Seek disconfirming evidence for load-bearing claims, composition edges, compatibility, recovery, and operational behavior.
4. Create an `audit-result-v1` JSON file with per-check results and evidence references. For brownfield pass, add an `assurance` assertion naming every reviewed impact, inspection, and finding ID, a complete scope review, and limitations.
5. Submit the result:

```bash
python3 ../../scripts/pyramid.py audit --project <project-root> --node GATE-205 --actor <actor> --result pass --evidence <audit-result.json> --json
python3 ../../scripts/pyramid.py audit --project <project-root> --node GATE-205 --actor <actor> --result fail --evidence <audit-result.json> --json
```

6. On failure, identify affected claims and recommend repair, impact reconciliation, approved expansion, or replan. The runtime moves executable failure to `needs-rework` and stales dependent task and inspection evidence.
7. Verify a parent only after required children, its joint gate, and applicable assurance coverage pass.
8. After the final intent passes, inspect lifecycle. Brownfield closure also requires complete controls and writes a change dossier plus the next baseline revision.

## Boundaries

- Never pass an audit from task status alone.
- Never use missing evidence as positive evidence.
- Prefer an independent auditor for critical joint and intent gates.
- A failed audit must remain visible in state and history until repaired or superseded.
- Never treat an audit assertion as evidence by itself; its IDs must resolve to sufficient canonical records.
