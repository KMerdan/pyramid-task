<!-- Generated from canonical proof contracts. Do not edit. -->
# Development harness

Use existing project tools. Implement only missing observation capability before outcome acceptance.
Capture inspect --harness <node> before executing checks. Inspect visual captures, not merely their existence.
A missing/failed observation blocks its claim, not independent authorized work. Never weaken acceptance to pass.
Keep result, evidence and limitations separate. A fresh guard is invocation authority, not reviewed source or host permission.

## INTENT-001: Safe operation outcome

- `EVREQ-INTENT-01` covers AC-INTENT-01 by reusing `TASK-201/EVREQ-201-01`; no duplicate execution.

## OUTCOME-010: Validated execution capability

- `EVREQ-OUTCOME-01` covers AC-OUTCOME-01 by reusing `TASK-201/EVREQ-201-01`; no duplicate execution.

## RESEARCH-101: Validate operation schema stability

### EVREQ-101-01 → AC-101-01

- Shared definition: `RESEARCH-101/EVREQ-101-01`
- Method: review; environment: Current repository files; recorded compatibility examples
- Procedure: Inspect the operation-plan definitions and existing tests; retain a compatibility note citing the inspected cases.
- Inputs: src/operation-plan/**/*, tests/**/*
- Required observations: internal
- external not applicable: Repository analysis has no runtime interaction
- visual not applicable: This claim inspects schema semantics, not a rendered artifact

## CONTRACT-102: Define executor contract

### EVREQ-102-01 → AC-102-01

- Shared definition: `CONTRACT-102/EVREQ-102-01`
- Method: command; environment: Isolated local test process with the repository's existing recovery fixtures
- Procedure: Run the existing contract tests for invalid input, execution failure and rollback.
- Inputs: src/contracts/**/*, tests/contracts/**/*
- Required observations: external, internal
- visual not applicable: This executor is a headless library; no rendered surface belongs to this outcome

## TASK-201: Implement safe executor

### EVREQ-201-01 → AC-201-01, AC-201-02

- Shared definition: `TASK-201/EVREQ-201-01`
- Method: command; environment: Isolated local test process with the repository's existing recovery fixtures
- Procedure: Run the existing executor scenarios for valid input, rejected input and recoverable failure; inspect returned behavior and retained internal state.
- Inputs: src/executor/**/*, src/contracts/**/*, tests/**/*
- Required observations: external, internal
- visual not applicable: This executor is a headless library; no rendered surface belongs to this outcome

## GATE-290: Audit execution composition

- `EVREQ-290-01` covers AC-290-01 by reusing `TASK-201/EVREQ-201-01`; no duplicate execution.
