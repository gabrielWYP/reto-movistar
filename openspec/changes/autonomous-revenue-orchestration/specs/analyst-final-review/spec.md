# Analyst Final Review Specification

## Purpose

Define the analyst's single, auditable review of an immutable consolidated output without introducing
human stage gates into successful autonomous execution.

## Requirements

### Requirement: No intermediate analyst gate

The normal run MUST continue between specialists without analyst approval. Intermediate evidence MAY
be viewed, but annotations or delayed viewing MUST NOT authorize, block, reorder, or skip a workflow
transition.

#### Scenario: Analyst does not inspect an intermediate phase

- GIVEN Billing receives PASS and the analyst has not viewed its output
- WHEN the run advances
- THEN Collections begins without analyst approval
- AND the missing view does not alter the audit sequence

#### Scenario: Analyst annotates intermediate evidence

- GIVEN a successful run is still executing
- WHEN the analyst records a non-decision annotation on visible phase evidence
- THEN the annotation is retained separately
- AND it does not change any result, verdict, or transition

### Requirement: Immutable final review package

After all three specialists receive PASS, the system MUST create one immutable final package containing
the bound revisions, normalized phase outputs, Judge histories, cross-phase lineage, data-quality
limitations, recommendations, and execution metadata.

#### Scenario: Produce a completed package

- GIVEN Billing, Collections, and BI have each received PASS
- WHEN the final Judge decision is committed
- THEN one immutable final package is made available to the analyst
- AND every conclusion is traceable through Judge-approved evidence to the bound CSV revision

#### Scenario: Detect incomplete package lineage

- GIVEN a required output, verdict, or evidence link is absent
- WHEN final package creation is attempted
- THEN the package is not marked review-ready
- AND the run is escalated to MANUAL_REVIEW with the missing lineage identified

### Requirement: Manual-review package

When a Judge emits MANUAL_REVIEW, the system MUST stop autonomous execution and provide one immutable
review package containing all committed work, the blocking verdict, attempts, unresolved checks, and
the next phase that was prevented.

#### Scenario: Review a stopped run

- GIVEN a specialist cannot receive PASS within its permitted attempts
- WHEN MANUAL_REVIEW is committed
- THEN downstream specialists do not start
- AND the analyst receives a package that identifies the blocker and all available evidence

### Requirement: Auditable final validation

The analyst MUST be able to accept or reject a review-ready package and MAY add an annotation. The
decision MUST identify the analyst, package revision, outcome, reason, and time. It MUST NOT mutate
specialist outputs, Judge verdicts, or source evidence.

#### Scenario: Accept a completed package

- GIVEN an immutable completed package is review-ready
- WHEN the analyst accepts it with a valid review request
- THEN an acceptance record is appended for that exact package revision
- AND the run remains completed with analyst validation recorded

#### Scenario: Reject a package

- GIVEN a completed or manual-review package is review-ready
- WHEN the analyst rejects it with a reason
- THEN a rejection record is appended
- AND no automatic rerun or external financial action is triggered

### Requirement: Idempotent review decision

Repeating the same review request with the same idempotency key and content MUST return the original
decision. Reusing the key for a different decision or package revision MUST be rejected.

#### Scenario: Replay final acceptance

- GIVEN an acceptance request has been committed
- WHEN the identical request is replayed with its original idempotency key
- THEN the original review record is returned
- AND no duplicate review event is appended

#### Scenario: Conflict on review replay

- GIVEN a review idempotency key is already bound to one decision
- WHEN it is reused for a different outcome or package revision
- THEN the request is rejected as a conflict
- AND the committed review record remains unchanged
