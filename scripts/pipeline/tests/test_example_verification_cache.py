"""Tests for lib/example_verification/cache.py (rollout step C2): key
stability, hit/miss/stale matrix, and the never-cache list for
non-deterministic outcomes."""
from __future__ import annotations

from lib.example_verification.cache import CacheEntry, ResultCache, cache_key, stale_reason


def test_cache_key_is_stable_for_identical_inputs():
    k1 = cache_key("sha1", "python", "head1", "tc-fp-1", "1")
    k2 = cache_key("sha1", "python", "head1", "tc-fp-1", "1")
    assert k1 == k2


def test_cache_key_changes_when_any_component_changes():
    base = cache_key("sha1", "python", "head1", "tc-fp-1", "1")
    assert cache_key("sha2", "python", "head1", "tc-fp-1", "1") != base
    assert cache_key("sha1", "typescript", "head1", "tc-fp-1", "1") != base
    assert cache_key("sha1", "python", "head2", "tc-fp-1", "1") != base
    assert cache_key("sha1", "python", "head1", "tc-fp-2", "1") != base
    assert cache_key("sha1", "python", "head1", "tc-fp-1", "2") != base


def test_put_and_get_roundtrip(tmp_path):
    rc = ResultCache("testfam", "python", root=tmp_path)
    key = cache_key("sha1", "python", "head1", "tc-fp-1", "1")
    entry = CacheEntry(status="PASS", proof_tier=3, clone_head="head1",
                        toolchain_version="tc-fp-1", runners_module_version="1")
    stored = rc.put(key, entry)
    assert stored is True
    fetched = rc.get(key, want_tier=2)
    assert fetched is not None
    assert fetched.status == "PASS"
    assert fetched.proof_tier == 3


def test_get_miss_for_unknown_key(tmp_path):
    rc = ResultCache("testfam", "python", root=tmp_path)
    assert rc.get("no-such-key", want_tier=1) is None


def test_get_miss_when_stored_tier_below_requested_and_not_a_failure(tmp_path):
    rc = ResultCache("testfam", "python", root=tmp_path)
    key = cache_key("sha1", "python", "head1", "tc-fp-1", "1")
    rc.put(key, CacheEntry(status="PASS", proof_tier=1))
    assert rc.get(key, want_tier=3) is None


def test_get_hit_for_deterministic_failure_regardless_of_requested_tier(tmp_path):
    # A real SYNTAX-ERROR found at tier 1 still answers a tier-3 request --
    # compiling can't un-fail a block already known to be syntactically broken.
    rc = ResultCache("testfam", "java", root=tmp_path)
    key = cache_key("sha1", "java", "head1", "tc-fp-1", "1")
    rc.put(key, CacheEntry(status="BLOCKED-WITH-REASON", reason="SYNTAX-ERROR", proof_tier=1))
    hit = rc.get(key, want_tier=3)
    assert hit is not None
    assert hit.reason == "SYNTAX-ERROR"


def test_never_caches_toolchain_unavailable(tmp_path):
    rc = ResultCache("testfam", "java", root=tmp_path)
    key = cache_key("sha1", "java", "head1", "tc-fp-1", "1")
    stored = rc.put(key, CacheEntry(status="BLOCKED-WITH-REASON", reason="TOOLCHAIN-UNAVAILABLE", proof_tier=0))
    assert stored is False
    assert rc.get(key, want_tier=0) is None


def test_never_caches_timeout(tmp_path):
    rc = ResultCache("testfam", "python", root=tmp_path)
    key = cache_key("sha1", "python", "head1", "tc-fp-1", "1")
    stored = rc.put(key, CacheEntry(status="BLOCKED-WITH-REASON", reason="TIMEOUT", proof_tier=0))
    assert stored is False


def test_never_caches_budget_exhausted(tmp_path):
    rc = ResultCache("testfam", "python", root=tmp_path)
    key = cache_key("sha1", "python", "head1", "tc-fp-1", "1")
    stored = rc.put(key, CacheEntry(status="BLOCKED-WITH-REASON", reason="BUDGET-EXHAUSTED", proof_tier=0))
    assert stored is False


def test_cache_persists_across_instances(tmp_path):
    key = cache_key("sha1", "python", "head1", "tc-fp-1", "1")
    rc1 = ResultCache("testfam", "python", root=tmp_path)
    rc1.put(key, CacheEntry(status="PASS", proof_tier=3))
    rc2 = ResultCache("testfam", "python", root=tmp_path)
    fetched = rc2.get(key, want_tier=1)
    assert fetched is not None
    assert fetched.status == "PASS"


def test_cache_file_path_is_scoped_per_family_platform(tmp_path):
    rc = ResultCache("pdf", "python", root=tmp_path)
    assert rc.path == tmp_path / "pdf_python" / "cache.json"


def test_stale_reason_clone_head_changed():
    entry = CacheEntry(status="PASS", proof_tier=3, clone_head="old_head")
    assert stale_reason(entry, clone_head="new_head") == "clone_head"


def test_stale_reason_toolchain_version_changed():
    entry = CacheEntry(status="PASS", proof_tier=3, clone_head="h", toolchain_version="1.0")
    assert stale_reason(entry, clone_head="h", toolchain_version="2.0") == "toolchain_version"


def test_stale_reason_runners_version_changed():
    entry = CacheEntry(status="PASS", proof_tier=3, clone_head="h",
                        toolchain_version="1.0", runners_module_version="1")
    assert stale_reason(entry, clone_head="h", toolchain_version="1.0",
                         runners_module_version="2") == "runners_version"


def test_stale_reason_snippet_edited():
    entry = CacheEntry(status="PASS", proof_tier=3, code_sha256="abc")
    assert stale_reason(entry, current_code_sha256="def") == "snippet_edited"


def test_stale_reason_none_when_everything_matches():
    entry = CacheEntry(status="PASS", proof_tier=3, clone_head="h",
                        toolchain_version="1.0", runners_module_version="1",
                        code_sha256="abc")
    assert stale_reason(
        entry, clone_head="h", toolchain_version="1.0",
        runners_module_version="1", current_code_sha256="abc",
    ) is None


def test_stale_reason_priority_order_clone_head_first():
    entry = CacheEntry(status="PASS", proof_tier=3, clone_head="old",
                        toolchain_version="old_tc")
    # Both clone_head and toolchain_version differ -- clone_head must win.
    assert stale_reason(entry, clone_head="new", toolchain_version="new_tc") == "clone_head"
