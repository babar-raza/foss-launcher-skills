"""B9 (MT074): lib/content_propagation_state.py -- single source of per-product propagation truth.

Fixtures deliberately span several languages/families so nothing here depends on one product.
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

# sys.path is set by tests/conftest.py
import content_propagation_state as cps

_LIB_DIR = Path(cps.__file__).resolve().parent
_PIPELINE_DIR = _LIB_DIR.parent
_SCRIPTS_DIR = _PIPELINE_DIR.parent

PRODUCTS = [("fam-a", "java"), ("fam-b", "python"), ("fam-c", "typescript"), ("fam-d", "go")]
SHA1, SHA2, SHA3 = "1" * 40, "2" * 40, "3" * 40


@pytest.fixture(autouse=True)
def _state(tmp_path):
    path = tmp_path / "content_propagation_state.json"
    cps.configure(path)
    yield path
    cps.configure(None)


def _drift(f, p, head=SHA2, ksha=SHA1, **kw):
    args = dict(
        upstream_head=head, knowledge_sha=ksha, tier="SOURCE", release_state="released",
        ahead_by=3, files_seen=10, source_files=4, api_surface_touched=False,
        truncated=False, ground_truth_tier="GT-2", observed_at="2026-10-07T00:00:00Z",
    )
    args.update(kw)
    return cps.record_drift(f, p, **args)


def _propagate(f, p, sha, **kw):
    args = dict(
        content_propagated_sha=sha, content_propagated_knowledge_commit="k" * 40,
        local_only=False, capability_units=[], gate_verdict="PASS",
    )
    args.update(kw)
    return cps.record_propagation(f, p, **args)


# ── compute_status ───────────────────────────────────────────────────────────

def _ok(**kw):
    rec = {"gate_verdict": "PASS", "content_propagated_knowledge_commit": "k" * 40}
    rec.update(kw)
    return rec


class TestComputeStatus:
    def test_unrecorded_without_propagated_sha(self):
        assert cps.compute_status({"upstream_head": SHA1}) == "UNRECORDED"
        assert cps.compute_status({"upstream_head": SHA1, "content_propagated_sha": None}) == "UNRECORDED"

    def test_drifted_when_head_differs(self):
        assert cps.compute_status(_ok(upstream_head=SHA2, content_propagated_sha=SHA1)) == "DRIFTED"

    def test_drifted_when_head_unknown(self):
        assert cps.compute_status(_ok(upstream_head=None, content_propagated_sha=SHA1)) == "DRIFTED"

    def test_propagated_and_local(self):
        rec = _ok(upstream_head=SHA1, content_propagated_sha=SHA1)
        assert cps.compute_status(rec) == "PROPAGATED"
        assert cps.compute_status({**rec, "local_only": True}) == "PROPAGATED_LOCAL"

    @pytest.mark.parametrize("verdict", [None, "FAIL", "", "pass", {"verdict": "PASS"}])
    def test_matching_sha_without_pass_verdict_is_never_propagated(self, verdict):
        rec = _ok(upstream_head=SHA1, content_propagated_sha=SHA1, gate_verdict=verdict)
        assert cps.compute_status(rec) == "DRIFTED"

    def test_pass_needs_knowledge_commit_or_units(self):
        base = {"upstream_head": SHA1, "content_propagated_sha": SHA1, "gate_verdict": "PASS"}
        assert cps.compute_status(base) == "DRIFTED"
        assert cps.compute_status({**base, "content_propagated_knowledge_commit": "", "capability_units": []}) == "DRIFTED"
        assert cps.compute_status({**base, "capability_units": [{"id": "u"}]}) == "PROPAGATED"
        assert cps.compute_status({**base, "content_propagated_knowledge_commit": "k" * 40}) == "PROPAGATED"


class TestTransitions:
    @pytest.mark.parametrize("family,platform", PRODUCTS)
    def test_full_lifecycle(self, family, platform):
        assert cps.read_state(family, platform) is None
        assert _drift(family, platform, head=SHA1)["status"] == "UNRECORDED"
        assert _propagate(family, platform, SHA1)["status"] == "PROPAGATED"
        # upstream moves on -> DRIFTED, propagation fields preserved
        rec = _drift(family, platform, head=SHA2)
        assert rec["status"] == "DRIFTED"
        assert rec["content_propagated_sha"] == SHA1
        # local-only propagation of the new head
        assert _propagate(family, platform, SHA2, local_only=True)["status"] == "PROPAGATED_LOCAL"
        assert cps.read_state(family, platform)["status"] == "PROPAGATED_LOCAL"
        # pushed
        assert _propagate(family, platform, SHA2, local_only=False)["status"] == "PROPAGATED"

    def test_propagate_before_any_drift_record_is_drifted(self):
        rec = _propagate("fam-a", "java", SHA1)  # upstream_head still unknown
        assert rec["status"] == "DRIFTED"


# ── the core invariants ──────────────────────────────────────────────────────

class TestInvariants:
    def test_hand_edited_sha_without_pass_verdict_stays_drifted(self, _state):
        _drift("fam-a", "java", head=SHA1)
        data = json.loads(_state.read_text(encoding="utf-8"))
        rec = data["products"]["fam-a/java"]
        rec["content_propagated_sha"] = SHA1
        rec["status"] = "PROPAGATED"                      # even a hand-forged status field
        _state.write_text(json.dumps(data), encoding="utf-8")
        assert cps.read_state("fam-a", "java")["status"] == "DRIFTED"
        assert cps.read_all()["products"]["fam-a/java"]["status"] == "DRIFTED"
        # and the next legitimate write re-derives it instead of trusting the forged field
        assert _drift("fam-a", "java", head=SHA1)["status"] == "DRIFTED"

    def test_record_propagation_requires_a_pass_verdict(self):
        for verdict in (None, "FAIL", "", {"verdict": "PASS"}):
            with pytest.raises(ValueError, match="gate_verdict"):
                _propagate("fam-a", "java", SHA1, gate_verdict=verdict)
        assert cps.read_state("fam-a", "java") is None

    def test_direct_call_with_no_verdict_and_no_units_raises(self):
        with pytest.raises(ValueError):
            cps.record_propagation("fam-a", "java", content_propagated_sha=SHA1,
                                   content_propagated_knowledge_commit=None, local_only=False,
                                   capability_units=[], gate_verdict=None)

    def test_requires_knowledge_commit_or_units(self):
        with pytest.raises(ValueError, match="knowledge"):
            _propagate("fam-a", "java", SHA1, content_propagated_knowledge_commit=None, capability_units=[])
        _propagate("fam-a", "java", SHA1, content_propagated_knowledge_commit=None,
                   capability_units=[{"id": "u", "dispositions": {"docs": {"status": "satisfied"}}}])

    def test_pending_cells_rejected(self):
        units = [{"id": "u", "dispositions": {"docs": {"status": "satisfied"}, "kb": {"status": "pending"}}}]
        with pytest.raises(ValueError, match="pending"):
            _propagate("fam-a", "java", SHA1, capability_units=units)
        assert cps.read_state("fam-a", "java") is None

    @pytest.mark.parametrize("bad", ["abc", "1" * 39, "1" * 41, "g" * 40, "main", "1" * 40 + "\n"])
    def test_sha_must_be_40_hex(self, bad):
        with pytest.raises(ValueError, match="40"):
            _propagate("fam-a", "java", bad)

    def test_sha_normalised_to_lowercase(self):
        _drift("fam-a", "java", head="a" * 40)
        assert _propagate("fam-a", "java", "A" * 40)["content_propagated_sha"] == "a" * 40

    def test_knowledge_only_change_never_marks_propagated(self):
        _drift("fam-a", "java", head=SHA1, ksha=SHA1)
        rec = _drift("fam-a", "java", head=SHA1, ksha=SHA1, tier="NO_CHANGE")
        assert rec["knowledge_sha"] == rec["upstream_head"]  # knowledge fully current...
        assert rec["status"] == "UNRECORDED"                 # ...yet NOT propagated
        # even when knowledge catches up to a newer head after a propagation of an older one
        _propagate("fam-a", "java", SHA1)
        rec = _drift("fam-a", "java", head=SHA3, ksha=SHA3)
        assert rec["status"] == "DRIFTED"

    def test_record_drift_never_alters_propagation_fields(self):
        units = [{"id": "u1", "symbols": ["b", "a"], "availability": "released",
                  "dispositions": {"docs": {"status": "satisfied", "evidence_paths": ["x.md"]}}}]
        _propagate("fam-b", "python", SHA1, capability_units=units, gate_verdict="PASS", local_only=True)
        before = cps.read_state("fam-b", "python")
        _drift("fam-b", "python", head=SHA3, ksha=SHA3, tier="API_TOUCHED", api_surface_touched=True)
        after = cps.read_state("fam-b", "python")
        for field in cps.PROPAGATION_FIELDS:
            assert after[field] == before[field], field
        assert after["tier"] == "API_TOUCHED"

    def test_record_drift_signature_has_no_propagation_parameters(self):
        import inspect
        params = set(inspect.signature(cps.record_drift).parameters)
        assert not params & set(cps.PROPAGATION_FIELDS)
        assert "status" not in params

    def test_rejects_bad_enums(self):
        with pytest.raises(ValueError):
            _drift("fam-a", "java", tier="BOGUS")
        with pytest.raises(ValueError):
            _drift("fam-a", "java", release_state="maybe")
        with pytest.raises(ValueError):
            _drift("fam-a", "java", ground_truth_tier="GT-9")
        with pytest.raises(ValueError):
            _propagate("fam-a", "java", SHA1, capability_units=[
                {"id": "u", "dispositions": {"docs": {"status": "done"}}}])
        with pytest.raises(ValueError):
            _propagate("fam-a", "java", SHA1, capability_units=[
                {"id": "u", "dispositions": {"nowhere": {"status": "pending"}}}])
        with pytest.raises(ValueError):
            _propagate("fam-a", "java", "")

    def test_capability_units_normalized_and_sorted(self):
        _propagate("fam-c", "typescript", SHA1, capability_units=[
            {"id": "z", "symbols": ["B", "A", "A"], "dispositions": {
                "kb": {"status": "none_justified", "evidence_paths": ["b", "a"]}}},
            {"id": "a", "symbols": []},
        ])
        units = cps.read_state("fam-c", "typescript")["capability_units"]
        assert [u["id"] for u in units] == ["a", "z"]
        assert units[1]["symbols"] == ["A", "B"]
        assert units[1]["dispositions"]["kb"]["evidence_paths"] == ["a", "b"]

    def test_corrupt_file_reads_empty_but_write_refuses(self, _state):
        _state.write_text("{not json", encoding="utf-8")
        assert cps.read_all() == {"schema_version": 1, "products": {}}
        assert cps.read_state("fam-a", "java") is None
        with pytest.raises(cps.StateCorrupt):
            _drift("fam-a", "java")
        assert _state.read_text(encoding="utf-8") == "{not json"  # untouched


class TestMonotonic:
    def test_refuses_to_lower_or_replace_a_recorded_sha(self):
        _drift("fam-a", "java", head=SHA2)
        _propagate("fam-a", "java", SHA2)
        for other in (SHA1, SHA3):     # older, and unrelated
            with pytest.raises(cps.PropagationRegression):
                _propagate("fam-a", "java", other)
        assert cps.read_state("fam-a", "java")["content_propagated_sha"] == SHA2

    def test_same_sha_is_idempotent_and_local_to_pushed_allowed(self):
        _drift("fam-a", "java", head=SHA1)
        _propagate("fam-a", "java", SHA1, local_only=True)
        assert _propagate("fam-a", "java", SHA1, local_only=False)["status"] == "PROPAGATED"

    def test_advance_to_the_observed_upstream_head_is_allowed(self):
        _drift("fam-a", "java", head=SHA1)
        _propagate("fam-a", "java", SHA1)
        _drift("fam-a", "java", head=SHA2)
        assert _propagate("fam-a", "java", SHA2)["content_propagated_sha"] == SHA2

    def test_caller_supplied_predicate_decides(self):
        _drift("fam-a", "java", head=SHA1)
        _propagate("fam-a", "java", SHA1)
        calls = []

        def descendant(old, new):
            calls.append((old, new))
            return True

        _propagate("fam-a", "java", SHA3, is_descendant=descendant)       # not the observed head, but a descendant
        assert calls == [(SHA1, SHA3)]
        with pytest.raises(cps.PropagationRegression):
            _propagate("fam-a", "java", SHA2, is_descendant=lambda o, n: False)
        with pytest.raises(cps.PropagationRegression):
            _propagate("fam-a", "java", SHA2, is_descendant=lambda o, n: None)   # unknown is not "yes"
        cps.configure(cps.state_path(), is_descendant=lambda o, n: True)
        assert _propagate("fam-a", "java", SHA2)["content_propagated_sha"] == SHA2

    def test_force_reason_overrides_and_is_logged(self, caplog):
        _drift("fam-a", "java", head=SHA2)
        _propagate("fam-a", "java", SHA2)
        with caplog.at_level("WARNING"):
            rec = _propagate("fam-a", "java", SHA1, force_reason="upstream force-pushed; verified by hand")
        assert rec["content_propagated_sha"] == SHA1
        assert "force-pushed" in caplog.text and SHA2 in caplog.text
        assert rec["volatile"]["force_overrides"] == [
            {"from": SHA2, "to": SHA1, "reason": "upstream force-pushed; verified by hand"}]
        with pytest.raises(cps.PropagationRegression):
            _propagate("fam-a", "java", SHA3, force_reason="   ")          # blank reason is not a reason


# ── determinism / idempotency / canonicalisation ─────────────────────────────

class TestDeterminism:
    def test_byte_identical_idempotency(self, _state):
        for f, p in PRODUCTS:
            _drift(f, p)
            _propagate(f, p, SHA1)
        first = _state.read_bytes()
        mtime = _state.stat().st_mtime_ns
        for f, p in PRODUCTS:
            _drift(f, p)
            _propagate(f, p, SHA1)
        assert _state.read_bytes() == first
        assert _state.stat().st_mtime_ns == mtime  # not even rewritten

    def test_file_format(self, _state):
        _drift("fam-a", "java")
        raw = _state.read_bytes()
        assert raw.endswith(b"\n") and not raw.endswith(b"\n\n")
        assert b"\r" not in raw
        data = json.loads(raw)
        assert data["schema_version"] == 1
        assert list(data["products"]) == ["fam-a/java"]
        assert raw.decode("utf-8") == json.dumps(data, indent=2, sort_keys=True) + "\n"

    def test_insertion_order_does_not_change_bytes(self, tmp_path):
        a, b = tmp_path / "a.json", tmp_path / "b.json"
        cps.configure(a)
        for f, p in PRODUCTS:
            _drift(f, p)
        cps.configure(b)
        for f, p in reversed(PRODUCTS):
            _drift(f, p)
        assert a.read_bytes() == b.read_bytes()

    def test_canonical_for_compare_strips_volatile(self):
        _drift("fam-a", "java", observed_at="2026-01-01T00:00:00Z")
        s1 = cps.read_all()
        _drift("fam-a", "java", observed_at="2027-02-02T00:00:00Z", volatile_extra={"last_issue_number": 7})
        s2 = cps.read_all()
        assert s1 != s2
        assert cps.canonical_for_compare(s1) == cps.canonical_for_compare(s2)
        assert "volatile" not in json.dumps(cps.canonical_for_compare(s2))
        # input not mutated
        assert "volatile" in s2["products"]["fam-a/java"]

    def test_volatile_kept_when_observed_at_omitted(self):
        _drift("fam-a", "java", observed_at="2026-01-01T00:00:00Z")
        _drift("fam-a", "java", observed_at=None)
        assert cps.read_state("fam-a", "java")["volatile"]["observed_at"] == "2026-01-01T00:00:00Z"


# ── concurrency ──────────────────────────────────────────────────────────────

class TestConcurrency:
    def test_threads_do_not_lose_updates(self):
        keys = [(f"fam-{i}", plat) for i in range(6) for plat in ("java", "python")]
        errors: list[BaseException] = []

        def work(f, p):
            try:
                _drift(f, p, head=SHA2)
                _propagate(f, p, SHA2)
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=work, args=k) for k in keys]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        products = cps.read_all()["products"]
        assert sorted(products) == sorted(f"{f}/{p}" for f, p in keys)
        assert all(r["status"] == "PROPAGATED" for r in products.values())

    def test_processes_do_not_lose_updates(self, _state):
        script = (
            "import sys; sys.path.insert(0, sys.argv[1]); sys.path.insert(0, sys.argv[2]);"
            "import content_propagation_state as c; c.configure(sys.argv[3]);"
            "w = sys.argv[4]\n"
            "for i in range(4):\n"
            "    c.record_drift('fam-'+w, 'plat%d' % i, upstream_head='a'*40, knowledge_sha=None, tier='SOURCE',"
            " release_state='unknown', ahead_by=1, files_seen=1, source_files=1, api_surface_touched=False,"
            " truncated=False, ground_truth_tier='GT-2')\n"
        )
        procs = [
            subprocess.Popen(
                [sys.executable, "-c", script, str(_LIB_DIR), str(_PIPELINE_DIR), str(_state), str(w)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )
            for w in range(4)
        ]
        results = [(p.wait(timeout=180), p.stderr.read().decode("utf-8", "replace")) for p in procs]
        assert all(rc == 0 for rc, _ in results), results
        assert len(cps.read_all()["products"]) == 16


# ── transient Windows PermissionError handling (deterministic, injected) ─────

class Flaky:
    """Callable that raises PermissionError for its first `fail` calls, then delegates."""

    def __init__(self, real, fail, exc=None):
        self.real, self.fail, self.calls = real, fail, 0
        self.exc = exc or PermissionError(13, "Permission denied")

    def __call__(self, *a, **kw):
        self.calls += 1
        if self.calls <= self.fail:
            raise self.exc
        return self.real(*a, **kw)


class TestTransientPermissionErrors:
    def _cfg(self, state, **seams):
        sleeps: list[float] = []
        cfg = dict(sleep=sleeps.append, jitter=lambda: 0.0)
        cfg.update(seams)
        cps.configure(state, **cfg)
        return sleeps

    def test_replace_retried_until_success(self, _state):
        flaky = Flaky(os.replace, 4)
        sleeps = self._cfg(_state, replace=flaky)
        rec = _drift("fam-a", "java")
        assert rec["status"] == "UNRECORDED"
        assert flaky.calls == 5 and len(sleeps) == 4
        assert sleeps == sorted(sleeps)  # exponential, non-decreasing
        assert cps.read_state("fam-a", "java")["upstream_head"] == SHA2
        assert [p.name for p in _state.parent.iterdir() if p.name.endswith(".tmp")] == []

    def test_winerror_sharing_violation_is_also_retried(self, _state):
        exc = OSError(32, "used by another process")
        exc.winerror = 32
        flaky = Flaky(os.replace, 2, exc=exc)
        self._cfg(_state, replace=flaky)
        _drift("fam-a", "java")
        assert flaky.calls == 3

    def test_replace_budget_exhausted_raises_clear_error_and_loses_nothing(self, _state):
        _drift("fam-b", "python")
        before = _state.read_bytes()
        always = Flaky(os.replace, 10 ** 6)
        sleeps = self._cfg(_state, replace=always, retry_budget=0.5)
        with pytest.raises(cps.StateWriteError, match="replace"):
            _drift("fam-a", "java")
        assert sum(sleeps) <= 0.5 and len(sleeps) >= 2     # bounded, but actually retried
        assert _state.read_bytes() == before                # never half-written, never lost
        assert [p.name for p in _state.parent.iterdir() if p.name.endswith(".tmp")] == []
        # the lock was released: the next write works as soon as the fault clears
        self._cfg(_state)
        _drift("fam-a", "java")
        assert set(cps.read_all()["products"]) == {"fam-a/java", "fam-b/python"}

    def test_non_transient_replace_error_is_not_retried(self, _state):
        boom = Flaky(os.replace, 10, exc=OSError(28, "No space left on device"))
        sleeps = self._cfg(_state, replace=boom)
        with pytest.raises(cps.StateWriteError):
            _drift("fam-a", "java")
        assert boom.calls == 1 and sleeps == []

    def test_reads_retried_until_success(self, _state):
        _drift("fam-a", "java")
        flaky = Flaky(lambda p: Path(p).read_bytes(), 3)
        sleeps = self._cfg(_state, read_bytes=flaky)
        assert cps.read_state("fam-a", "java")["upstream_head"] == SHA2
        assert flaky.calls == 4 and len(sleeps) == 3
        flaky2 = Flaky(lambda p: Path(p).read_bytes(), 2)
        self._cfg(_state, read_bytes=flaky2)
        assert "fam-a/java" in cps.read_all()["products"]

    def test_read_inside_read_modify_write_retried(self, _state):
        _drift("fam-a", "java")
        flaky = Flaky(lambda p: Path(p).read_bytes(), 2)
        self._cfg(_state, read_bytes=flaky)
        _propagate("fam-a", "java", SHA2)
        assert flaky.calls >= 3
        assert cps.read_state("fam-a", "java")["status"] == "PROPAGATED"

    def test_read_budget_exhausted_raises_and_write_leaves_file_alone(self, _state):
        _drift("fam-a", "java")
        before = _state.read_bytes()
        always = Flaky(lambda p: Path(p).read_bytes(), 10 ** 6)
        self._cfg(_state, read_bytes=always, retry_budget=0.3)
        with pytest.raises(cps.StateReadError):
            cps.read_all()
        with pytest.raises(cps.StateWriteError):
            _drift("fam-b", "python")
        assert _state.read_bytes() == before

    def test_lock_acquire_permission_error_is_retried(self, _state):
        calls = {"n": 0}

        def flaky_acquire(lock):
            calls["n"] += 1
            if calls["n"] <= 3:
                raise PermissionError(13, "Permission denied")  # create while delete-pending (Windows)
            return lock.acquire()

        sleeps = self._cfg(_state, lock_acquire=flaky_acquire)
        _drift("fam-a", "java")
        assert calls["n"] == 4 and len(sleeps) == 3

    def test_configure_none_restores_real_seams(self, _state):
        self._cfg(_state, replace=Flaky(os.replace, 10 ** 6))
        cps.configure(_state)
        _drift("fam-a", "java")  # would raise if the always-failing replace were still injected


# ── source-scan: only the capability gate may mark a product propagated ──────

ALLOWED_RECORD_PROPAGATION_CALLERS = {"capability_surface_gate.py"}


def find_record_propagation_callers(root: Path) -> list[str]:
    """Relative paths of every non-test module under `root` that CALLS record_propagation."""
    found: list[str] = []
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        parts = set(path.relative_to(root).parts)
        if "tests" in parts or "__pycache__" in parts or ".venv" in parts or path.name == "content_propagation_state.py":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
                if name == "record_propagation":
                    found.append(rel)
                    break
    return found


class TestWriteBoundary:
    def test_scanner_detects_calls_and_ignores_comments(self, tmp_path):
        (tmp_path / "bad.py").write_text("import m\nm.record_propagation('a','b')\n", encoding="utf-8")
        (tmp_path / "bad2.py").write_text("from m import record_propagation\nrecord_propagation()\n", encoding="utf-8")
        (tmp_path / "ok.py").write_text("# record_propagation(x) is documented here\nx = 'record_propagation('\n", encoding="utf-8")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "t.py").write_text("record_propagation()\n", encoding="utf-8")
        assert find_record_propagation_callers(tmp_path) == ["bad.py", "bad2.py"]

    def test_only_capability_surface_gate_calls_record_propagation(self):
        callers = find_record_propagation_callers(_SCRIPTS_DIR)
        offenders = [c for c in callers if Path(c).name not in ALLOWED_RECORD_PROPAGATION_CALLERS]
        assert offenders == [], f"only capability_surface_gate.py may call record_propagation: {offenders}"
