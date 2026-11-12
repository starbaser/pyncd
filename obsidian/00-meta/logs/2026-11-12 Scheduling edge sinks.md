---
tags: [meta, log, hypergraph]
status: completed
---

# Scheduling edge sinks

Written by GPT-6 Astra, effort high.

## Task

The owner approved the prepared correction with “Yes. Make the patch.” The approval
followed a request to apply the exact scheduler change, validate its regressions and
the owning corpus, publish conditionally to the owner's fork, and update the consumer.

## Outcome

Edge columns claim only sinks already classified as eligible for that edge. A sink
with an external operand and an internal operand remains available to the interior
walk. The scalar regressions recover the expected output and saved parameter values.

## Features touched

- [[Hypergraph to Morphism]]: corrected edge placement and documented eligibility.
- [[Validation]]: added a graph validator discovered by the existing runner.

## Code changed

- [Graph conversion](../../../graphs/processing/Hypergraph2Morphism.py): filter edge
  claims by the eligible sink set while preserving ordinary interior injection.
- [Edge-sink validation](../../../graphs/validate_edge_sinks.py): six numerical and
  tape checks, with operation occurrence counts before and after conversion.
- [Repository instructions](../../../CLAUDE.md): replace the obsolete mirror notice
  and broken policy anchor with the existing owner-review policy.

## What was learned

A carried external input is insufficient evidence that a sink belongs at the leading
edge. Eligibility depends on the entire branch domain. Claiming a mixed-domain sink
early can prevent its internal producer and a required parameter tape save from being
scheduled.

## Negative results

On the unmodified revision the six-case regression produced two failures and four
passes. Both failures involved a mixed external/internal sink and a leading edge.
Native root deduplication and pathway collapse also failed to schedule the tape save.
Marking the prematurely placed operations as processed would retain the invalid
ordering, so that change was not used.

## Verification

The affected development corpus passed 61 targets with zero failures in 24.9 seconds:
`python validations/run_validations.py graphs/processing/Hypergraph2Morphism.py graphs/validate_edge_sinks.py`.
The selection includes the graph, backward, repository and notebook checks. Torch was
present. The six new cases preserve exact scalar outputs and tape values. The validator
also checks operation counts, including discarded arithmetic. The committed build and
consumer qualification are recorded separately by the consuming project.

## Gaps

No [[Open Gaps]] item was added or closed. The consumer's training objective still needs
qualification against the published correction.

## Follow-ups

Run the committed dependency checks before publication and then qualify the consumer's
native objective and optimizer lifecycle against the updated lock.
