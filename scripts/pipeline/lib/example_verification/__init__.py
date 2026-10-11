"""
lib/example_verification — shared example-verification package (S-63 owned).

CONTRACT: scripts/pipeline/lib/example_verification/__init__.py
  purpose: central home for everything that tokenizes markdown code fences,
           discovers toolchains, acquires disposable environments, runs code
           at any proof tier, and caches results -- replacing the per-skill
           split (S-120's own runners, S-63's tree-sitter-only smoke test,
           nothing at all in S-49/S-84) with one package every consumer
           calls (see docs/governance/planning-methodology.md's
           EXAMPLE-VERIFICATION-CENTRALIZATION mission record).
  inputs:  markdown text, ProductContext (clone-cache / factpack derived)
  outputs: VerificationReport / BlockResult (see result.py, landing in C2)
  owner_domain: content-quality
  requires_test: true

RUNNERS_MODULE_VERSION bumps whenever a runner's classification behavior
changes (same discipline as content_eval's CHECKS_MODULE_VERSION) -- stamped
into every VerificationReport so a stale cached/ledger result is visibly
distinguishable from a fresh one after a runner improves.
"""
from __future__ import annotations

# Deliberately NOT bumped by MT074: this value is stamped into sweeps/proofs
# and pinned by tests and swept data. Cache invalidation for the MT074
# semantics change (missing input file: cached RUNTIME-ERROR -> uncached
# FIXTURE-UNAVAILABLE) is cache.CACHE_SCHEMA_VERSION's job instead.
RUNNERS_MODULE_VERSION = "1"

__all__ = ["RUNNERS_MODULE_VERSION"]
