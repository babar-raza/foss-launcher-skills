# Mixed Historical and Current Plan (Fixture: should FAIL normalization)

## Sprint 3 Retrospective

We completed the API surface extraction in Sprint 3. The batch processor was also
finished and merged. The grounding ratio checks are now live in production.

The team agreed in Sprint 3 to defer the locale pipeline to Sprint 5.

## Current Objectives

The next priority is to improve the batch processor throughput. This is partially
implemented — the new worker pool is done but the queue drain logic is still spec-only.

The grounding ratio checks were completed (see above). We should also complete the
queue drain logic and then re-run the batch processor benchmarks.

Note: we still need to build the locale pipeline (see Sprint 3 notes above).

## Implementation Notes

The worker pool uses a fixed-size thread pool with backpressure signaling. This is
implemented in `scripts/pipeline/batch_processor.py`. The queue drain logic will
extend this module once it is written.

Recommended next action: complete the queue drain logic and benchmark.
