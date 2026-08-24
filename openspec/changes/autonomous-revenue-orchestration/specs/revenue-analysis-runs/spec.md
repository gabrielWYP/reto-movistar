# Revenue Analysis Runs Specification

## Purpose

Define the durable autonomous run that coordinates the three revenue specialists in one fixed,
recoverable, read-only workflow.

## Requirements

### Requirement: Revision-bound run creation

A run MUST bind exactly one immutable dataset revision and one compatible immutable ruleset revision.
It MUST reject missing, mutable, mismatched, or non-execution-ready references before work begins.

#### Scenario: Create an execution-ready run

- GIVEN compatible dataset and ruleset revisions are execution-ready
- WHEN Supervisor creates a run
- THEN the run records both revisions and a stable run identifier
- AND later revision changes cannot alter the run inputs

#### Scenario: Reject mismatched revisions

- GIVEN a ruleset revision belongs to a different dataset revision
- WHEN run creation is attempted
- THEN the request is rejected
- AND no executable run is created

### Requirement: Fixed sequential execution

The run MUST execute Billing, Collections, and BI in that exact order. Each specialist output MUST be
approved by its Judge gate before the next specialist starts. The workflow MUST NOT reorder, skip, or
run specialists concurrently.

#### Scenario: Complete the nominal sequence

- GIVEN an execution-ready run
- WHEN every specialist passes its Judge gate
- THEN the recorded sequence is Billing, Billing Judge, Collections, Collections Judge, BI, BI Judge
- AND the run becomes completed only after the final Judge passes

#### Scenario: Prevent an out-of-order transition

- GIVEN Billing has not received a PASS verdict
- WHEN Collections execution is requested
- THEN the transition is rejected
- AND no Collections output or execution attempt is recorded

### Requirement: Idempotent commands and phase work

Run creation, start, phase execution, and transition commands MUST be idempotent. Replaying a command
with the same key and input MUST return the previously committed result; conflicting reuse MUST fail
without overwriting evidence.

#### Scenario: Replay a committed phase command

- GIVEN a phase result was durably committed
- WHEN its command is replayed with the same key and input
- THEN the committed result is returned
- AND the specialist is not executed again

#### Scenario: Reject a conflicting phase command

- GIVEN a command key is already bound to one phase input
- WHEN it is reused with different input
- THEN the command is rejected as a conflict
- AND existing phase state and evidence remain unchanged

### Requirement: Durable recovery and single execution ownership

Dataset inputs, run state, outputs, verdicts, and audit history MUST survive loss and restart of the
application process. At most one execution owner MAY advance a run at a time; another owner MUST be
denied or observe the committed state without duplicating work.

#### Scenario: Resume after restart

- GIVEN the application stops after a durable transition
- WHEN service is restored with its durable storage available
- THEN the run resumes from the last committed transition
- AND no completed specialist or Judge step is repeated

#### Scenario: Storage unavailable during recovery

- GIVEN durable run storage is unavailable after restart
- WHEN recovery is attempted
- THEN the run is not advanced
- AND the unavailability is reported without constructing state from partial memory

#### Scenario: Competing execution owner

- GIVEN one owner is actively advancing a run
- WHEN another owner attempts to advance the same run
- THEN only one owner is authorized to commit transitions
- AND duplicate specialist execution is prevented

### Requirement: Read-only autonomous boundary

Autonomous runs MUST be limited to analysis, validation, evidence production, and recommendations.
They MUST NOT issue invoices, apply payments, contact customers, or mutate external business systems.

#### Scenario: Rule implies an external effect

- GIVEN a bound rule is interpreted as an external-effect action
- WHEN a specialist evaluates its plan
- THEN the action is refused
- AND the refusal is recorded as evidence without performing the effect

### Requirement: Operator-only restart checkpoint

The runner MUST recognize a checksummed, run-bound checkpoint request from durable storage without
exposing a public API. It MUST consume the request once at the specified committed state, return that
snapshot before another step, and permit a subsequent start replay to resume without duplicate work.

#### Scenario: Pause after a committed specialist step

- GIVEN an operator has placed a valid checkpoint for Billing judging on the durable PVC
- WHEN Billing output is committed and the runner observes the target state
- THEN it atomically archives the request as audit evidence and returns Billing judging
- AND replaying start after restart resumes with the Judge without executing Billing again

#### Scenario: Reject an untrusted checkpoint

- GIVEN a checkpoint is corrupt, symlinked, bound to another run, has an invalid digest, or names an illegal state
- WHEN the runner observes the request before its next advance
- THEN it fails closed without consuming the request
- AND the committed run state and specialist history remain unchanged
