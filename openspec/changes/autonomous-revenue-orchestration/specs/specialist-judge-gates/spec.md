# Specialist Judge Gates Specification

## Purpose

Define specialist evidence and authoritative Judge gates for bounded, fail-safe transitions.

## Requirements

### Requirement: Normalized specialist result

Each specialist MUST return status, validation checks, findings, evidence references, data quality,
recommended actions, and execution metadata. Evidence MUST identify inputs, rules, specialist,
attempt, and calculation or tool.

#### Scenario: Submit a complete specialist result

- GIVEN a specialist finishes an attempt using the bound revisions
- WHEN it submits its result to the Judge
- THEN the result conforms to the common contract
- AND every material finding is traceable to input and execution evidence

#### Scenario: Reject incomplete lineage

- GIVEN a material finding lacks a valid evidence reference or bound input revision
- WHEN the result is validated
- THEN the result fails a mandatory validation check
- AND it cannot receive PASS

### Requirement: Hard-gate precedence

The Judge MUST evaluate deterministic hard gates before qualitative criteria. A failed hard gate MUST
prevent PASS and MUST NOT be overridden by any model or specialist assessment.

#### Scenario: Model favors a hard-gate failure

- GIVEN a deterministic integrity, schema, lineage, or required-validation gate fails
- AND qualitative evaluation recommends acceptance
- WHEN the Judge resolves the verdict
- THEN PASS is prohibited
- AND the hard-gate failure is the authoritative reason

#### Scenario: All mandatory checks pass

- GIVEN all deterministic hard gates pass and qualitative criteria are satisfied
- WHEN the Judge resolves the first attempt
- THEN it emits PASS with supporting evidence
- AND the next workflow transition becomes eligible

### Requirement: Exactly one bounded retry

For a retryable first-attempt failure, the Judge SHALL emit RETRY with corrective constraints. A
specialist MUST receive no more than one retry. A non-retryable or post-retry failure MUST produce
MANUAL_REVIEW.

#### Scenario: Retry a correctable first failure

- GIVEN the first attempt fails for a declared retryable reason
- WHEN the Judge issues its verdict
- THEN the verdict is RETRY with the failed checks and bounded correction instructions
- AND exactly one additional attempt is permitted under the same phase identity

#### Scenario: Second attempt fails

- GIVEN a specialist has consumed its one permitted retry
- WHEN its second attempt does not qualify for PASS
- THEN the Judge emits MANUAL_REVIEW
- AND no third attempt or downstream specialist is started

#### Scenario: Non-retryable first failure

- GIVEN the first attempt has corrupt lineage, incompatible inputs, or another non-retryable defect
- WHEN the Judge resolves the verdict
- THEN it emits MANUAL_REVIEW without a retry
- AND downstream execution remains blocked

### Requirement: Deterministic fallback

Judge availability MUST NOT depend solely on model access. Without qualitative evaluation, the Judge
MUST apply the deterministic rubric. It MAY emit PASS only when every required criterion is
deterministically decidable and satisfied; otherwise it MUST emit RETRY or MANUAL_REVIEW.

#### Scenario: Model unavailable with complete deterministic evidence

- GIVEN model evaluation is unavailable
- AND all required criteria are deterministically decidable and satisfied
- WHEN the Judge evaluates the result
- THEN it MAY emit PASS using the deterministic fallback
- AND the verdict records fallback mode and unavailable dependency

#### Scenario: Model unavailable with undecidable criterion

- GIVEN model evaluation is unavailable
- AND a required qualitative criterion cannot be decided deterministically
- WHEN the Judge evaluates the result
- THEN it cannot emit PASS
- AND it emits RETRY or MANUAL_REVIEW based on remaining retry eligibility

### Requirement: Append-only Judge evidence

Every verdict MUST record phase, attempt, checks, rubric outcome, evidence references, decision mode,
and time. Re-evaluation MUST append a decision and MUST NOT replace a prior verdict.

#### Scenario: Inspect verdict history

- GIVEN a phase was retried after a Judge verdict
- WHEN its audit history is requested
- THEN both verdicts and their evidence are returned in decision order
- AND neither record has been rewritten
