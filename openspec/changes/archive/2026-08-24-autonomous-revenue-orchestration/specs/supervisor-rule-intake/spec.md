# Supervisor Rule Intake Specification

## Purpose

Define how Supervisor turns a complete CSV publication into immutable, traceable business rules that
are safe to use for autonomous revenue analysis.

## Requirements

### Requirement: Immutable dataset revision

Supervisor MUST create an immutable dataset revision only after all six required CSV sources pass
publication validation. The revision MUST preserve source identity, integrity evidence, profile
summary, and creation time, and MUST be the sole dataset reference accepted by rule intake.

#### Scenario: Publish a valid dataset

- GIVEN all six required CSV sources pass validation
- WHEN Supervisor publishes them
- THEN one immutable dataset revision is created with integrity and profile evidence
- AND business-rule intake becomes available for that revision

#### Scenario: Reject an incomplete publication

- GIVEN one or more required CSV sources are missing or invalid
- WHEN publication is attempted
- THEN no dataset revision is created
- AND rule intake and autonomous execution remain unavailable

### Requirement: Idempotent publication

Supervisor MUST treat a repeated publication request with the same idempotency key and content as the
same operation. Reusing that key with different content MUST be rejected without changing the stored
revision.

#### Scenario: Replay a successful publication

- GIVEN a publication request has already created a dataset revision
- WHEN the identical request is replayed with its original idempotency key
- THEN the existing revision is returned
- AND no duplicate revision or audit event is created

#### Scenario: Detect conflicting replay

- GIVEN an idempotency key is bound to a dataset revision
- WHEN that key is reused with different CSV content
- THEN the request is rejected as a conflict
- AND the original revision remains unchanged

### Requirement: Global and specialist rule questions

Supervisor SHALL request required global rules, including analysis date, objective, and scope, and
SHALL request contextual rules for Billing, Collections, and BI derived from the dataset profile.
Questions MUST identify their target, expected answer type, and whether an answer is mandatory.

#### Scenario: Generate contextual questions

- GIVEN a published dataset revision with a completed profile
- WHEN rule intake begins
- THEN global questions and questions for each of the three specialists are presented
- AND every question is traceable to a profile observation or declared analysis requirement

#### Scenario: Missing mandatory answer

- GIVEN at least one mandatory global or specialist answer is absent or invalid
- WHEN the analyst submits the answers
- THEN no executable ruleset is accepted
- AND validation identifies each unresolved question

### Requirement: Immutable ruleset revision

An accepted answer set MUST produce an immutable ruleset revision bound to exactly one dataset
revision. Changing an answer after acceptance MUST create a new ruleset revision and MUST NOT alter a
run already bound to an earlier revision.

#### Scenario: Accept a complete ruleset

- GIVEN all mandatory answers are valid for the referenced dataset revision
- WHEN the analyst submits the rules
- THEN an immutable ruleset revision is created
- AND every normalized rule retains its originating question and answer evidence

#### Scenario: Revise rules after run creation

- GIVEN a run references an accepted ruleset revision
- WHEN the analyst changes one or more answers
- THEN a new ruleset revision is created
- AND the existing run continues to reference its original ruleset revision

### Requirement: Safe execution plan

Supervisor MUST validate the resulting plan against the supported read-only analysis catalogue before
a run can start. Unsupported instructions, including financial or customer-contact effects, MUST be
rejected rather than translated into executable work.

#### Scenario: Reject an external-effect instruction

- GIVEN a rule requests invoice issuance, payment application, customer contact, or another external effect
- WHEN the ruleset is validated
- THEN the ruleset is not execution-ready
- AND the rejected instruction and reason are recorded for the analyst
