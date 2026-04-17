# Partially Validated Capabilities Plan (Fixture: should FAIL normalization)

## Capability Status

The new streaming batch processor is implemented and partially validated. It passes
unit tests but has not been run against a live knowledge model in production.
The grounding ratio integration is spec-only — the interface is designed but the
wiring to the audit pipeline is not yet written.

## Open Work

1. Run the streaming batch processor against the slides family
   - Relies on: streaming batch processor (partially validated) + grounding ratio integration (spec-only)
   - Files: `scripts/pipeline/batch_processor.py`
   - Validation: batch completes with 0 errors; grounding ratio >= 80%
   - Status: ready

## Recommended Next Item

Execute item 1: run the streaming batch processor against the slides family.
