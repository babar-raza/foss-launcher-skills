"""Behavioral-equivalence tests: does the ported LOGIC actually match
aspose.org's, not just "look similar on read-through"?

New 2026-08-29, closes TASK_BACKLOG.md SYNC-9's first slice: "functional
parity" claims across this repo's history have all been prose/read-through
judgments, never verified by running source's and target's actual code
against identical input and diffing the output. This file does that, for
the 3 artifacts in the 2026-08-29 sync whose logic is supposed to be
LITERALLY equivalent (near-verbatim or lightly-adapted ports) -- not for
the llms-* family, whose backing scripts were deliberately rewritten
(different subdomain iteration, different output shape), so there is no
meaningful "same input, same output" comparison to make there; that
distinction is itself a finding, not an oversight -- see
docs/parity/source-anchors.yaml's generalization notes per artifact.

Requires SOURCE_REPO_PATH (the aspose.org checkout). Skips cleanly when
unset -- same posture as detect_source_drift.py: this is not a CI gate on
runners without the source repo available, it's an agent/session-invoked
proof. Imports source modules READ-ONLY (a plain Python import never
writes to the source repo).
"""
import importlib.util
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_REPO_PATH = os.environ.get("SOURCE_REPO_PATH", "")

pytestmark = pytest.mark.skipif(
    not SOURCE_REPO_PATH, reason="SOURCE_REPO_PATH not set -- behavioral-equivalence proof needs aspose.org checked out"
)


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def source_session_identity():
    path = Path(SOURCE_REPO_PATH) / "scripts" / "pipeline" / "lib" / "session_identity.py"
    if not path.is_file():
        pytest.skip(f"source file not found at expected path: {path}")
    return _load_module("source_session_identity", path)


@pytest.fixture
def target_session_identity():
    path = REPO_ROOT / "scripts" / "pipeline" / "lib" / "session_identity.py"
    return _load_module("target_session_identity", path)


_IDENTITY_ENV_MATRIX = [
    {},
    {"AGENT_SESSION_ID": "abc-123"},
    {"CODEX_THREAD_ID": "codex-xyz"},
    {"CLAUDE_CODE_SESSION_ID": "claude-session-1"},
    {"AGENT_SESSION_ID": "abc-123", "CODEX_THREAD_ID": "codex-xyz", "CLAUDE_CODE_SESSION_ID": "claude-session-1"},
    {"CODEX_THREAD_ID": "codex-xyz", "CLAUDE_CODE_SESSION_ID": "claude-session-1"},
    {"AGENT_SESSION_ID": "   "},  # whitespace-only, must be treated as unset
]


@pytest.mark.parametrize("env", _IDENTITY_ENV_MATRIX)
def test_session_identity_resolve_matches_source(monkeypatch, source_session_identity, target_session_identity, env):
    for key in ("AGENT_SESSION_ID", "CODEX_THREAD_ID", "CLAUDE_CODE_SESSION_ID"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert source_session_identity.resolve() == target_session_identity.resolve()


@pytest.mark.parametrize("raw", ["abc/def:ghi 123", "plain-id", "a" * 100, "with spaces  and\ttabs"])
def test_session_identity_sanitize_matches_source(source_session_identity, target_session_identity, raw):
    assert source_session_identity.sanitize(raw) == target_session_identity.sanitize(raw)


def test_session_identity_resolve_sanitized_matches_source(monkeypatch, source_session_identity, target_session_identity):
    monkeypatch.delenv("AGENT_SESSION_ID", raising=False)
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "weird id/with:chars")
    assert source_session_identity.resolve_sanitized() == target_session_identity.resolve_sanitized()


@pytest.fixture
def source_check_module_consumption():
    path = Path(SOURCE_REPO_PATH) / "scripts" / "ci" / "checks" / "check_module_consumption.py"
    if not path.is_file():
        pytest.skip(f"source file not found at expected path: {path}")
    return _load_module("source_check_module_consumption", path)


@pytest.fixture
def target_check_module_consumption():
    path = REPO_ROOT / "scripts" / "ci" / "checks" / "check_module_consumption.py"
    return _load_module("target_check_module_consumption", path)


def test_find_real_consumers_matches_source_on_identical_fixture(
    tmp_path, source_check_module_consumption, target_check_module_consumption
):
    """Ported with NO functional changes (per docs/parity/source-anchors.yaml's
    own notes) -- this proves that claim, not just asserts it."""
    scan_root = tmp_path / "scripts"
    scan_root.mkdir()
    (scan_root / "my_module.py").write_text("x = 1\n", encoding="utf-8")
    (scan_root / "caller_a.py").write_text("from my_module import x\n", encoding="utf-8")
    (scan_root / "test_my_module.py").write_text("import my_module\n", encoding="utf-8")
    (scan_root / "unrelated.py").write_text("y = 2\n", encoding="utf-8")

    source_result = source_check_module_consumption.find_real_consumers(
        "scripts/my_module.py", scan_root=scan_root, repo_root=tmp_path
    )
    target_result = target_check_module_consumption.find_real_consumers(
        "scripts/my_module.py", scan_root=scan_root, repo_root=tmp_path
    )
    assert source_result == target_result
    assert [p.name for p in source_result] == ["caller_a.py"]


@pytest.fixture
def source_check_stale_file_regression():
    path = Path(SOURCE_REPO_PATH) / "scripts" / "ci" / "checks" / "check_stale_file_regression.py"
    if not path.is_file():
        pytest.skip(f"source file not found at expected path: {path}")
    return _load_module("source_check_stale_file_regression", path)


@pytest.fixture
def target_check_stale_file_regression():
    path = REPO_ROOT / "scripts" / "ci" / "checks" / "check_stale_file_regression.py"
    return _load_module("target_check_stale_file_regression", path)


_REGRESSION_MATRIX = [
    ("old", "old", "new"),      # silent revert -> True
    ("new", "old", "new"),      # already incorporates the change -> False
    ("other", "old", "new"),    # neither match -> False
    ("old", "old", None),       # intervening had no comparable blob -> False
    ("old", None, "new"),       # file newly created by intervening -> False
]


@pytest.mark.parametrize("proposed,parent,intervening", _REGRESSION_MATRIX)
def test_detect_regression_matches_source(
    source_check_stale_file_regression, target_check_stale_file_regression, proposed, parent, intervening
):
    source_result = source_check_stale_file_regression.detect_regression(proposed, parent, intervening)
    target_result = target_check_stale_file_regression.detect_regression(proposed, parent, intervening)
    assert source_result == target_result


@pytest.fixture
def source_advisory_lock():
    path = Path(SOURCE_REPO_PATH) / "scripts" / "pipeline" / "lib" / "advisory_lock.py"
    if not path.is_file():
        pytest.skip(f"source file not found at expected path: {path}")
    return _load_module("source_advisory_lock", path)


@pytest.fixture
def target_advisory_lock():
    path = REPO_ROOT / "scripts" / "pipeline" / "lib" / "advisory_lock.py"
    return _load_module("target_advisory_lock", path)


def test_advisory_lock_acquire_release_matches_source(tmp_path, source_advisory_lock, target_advisory_lock):
    source_path = tmp_path / "source.lock"
    target_path = tmp_path / "target.lock"
    source_lock = source_advisory_lock.FileLock(source_path)
    target_lock = target_advisory_lock.FileLock(target_path)
    source_lock.acquire()
    target_lock.acquire()
    assert source_path.exists() == target_path.exists() is True
    source_lock.release()
    target_lock.release()
    assert source_path.exists() == target_path.exists() is False


def test_advisory_lock_timeout_behavior_matches_source(tmp_path, source_advisory_lock, target_advisory_lock):
    for mod, path in ((source_advisory_lock, tmp_path / "s.lock"), (target_advisory_lock, tmp_path / "t.lock")):
        holder = mod.FileLock(path)
        holder.acquire()
        waiter = mod.FileLock(path, timeout=0.2, poll=0.05)
        with pytest.raises(mod.LockTimeout):
            waiter.acquire()
        holder.release()


_TASKCARD_STORE_PLAIN_DEPS = ("schema_validators", "advisory_lock")


@pytest.fixture
def _isolated_sys_path():
    """taskcard_store.py's own top-level code self-registers its directory
    onto sys.path (needed for its internal `from schema_validators import`
    / `from advisory_lock import` to resolve) -- for BOTH the source and
    target copies loaded below. Left uncleaned, that leaks aspose.org's
    entire scripts/pipeline/lib/ directory (dozens of modules, e.g.
    knowledge_core.py) onto sys.path for the REST of the pytest session,
    which can silently shadow a same-named target module in a totally
    unrelated LATER test (found live: this exact leak broke
    tests/test_evaluator_new.py by resolving its knowledge_core import from
    aspose.org's file instead of this repo's own).

    A second, subtler issue this also guards against: taskcard_store.py's
    internal imports (`from schema_validators import ...`, `from
    advisory_lock import ...`) use PLAIN module names, which Python caches
    in sys.modules by that plain name. sys.modules[name] for those two
    specific names is snapshotted and restored EXACTLY (not just "delete if
    new") -- a generic "delete brand-new keys" diff is not enough: if
    "schema_validators" already had a REAL entry before this fixture ran
    (e.g. some other test file imported it directly), that key is not
    "new," so a delete-new-keys-only cleanup would silently leave whatever
    this fixture's own loading overwrote it with, never restoring the
    original value (found live while writing this fixture's own test).
    Any OTHER brand-new sys.modules entries (e.g. the synthetic
    "source_taskcard_store"/"target_taskcard_store" names) are still
    cleaned up via the coarser new-keys diff, which is safe for those since
    nothing else in this session uses those synthetic names."""
    path_before = list(sys.path)
    modules_before = set(sys.modules.keys())
    plain_dep_values_before = {dep: sys.modules.get(dep) for dep in _TASKCARD_STORE_PLAIN_DEPS}
    yield
    sys.path[:] = path_before
    for name in set(sys.modules.keys()) - modules_before:
        if name not in _TASKCARD_STORE_PLAIN_DEPS:
            del sys.modules[name]
    for dep, original in plain_dep_values_before.items():
        if original is None:
            sys.modules.pop(dep, None)
        else:
            sys.modules[dep] = original


def _load_taskcard_store_fresh(name: str, lib_dir: Path):
    """Force taskcard_store.py's internal `from schema_validators import`/
    `from advisory_lock import` to re-resolve from THIS lib_dir specifically.

    Two things must both be true, not just one:
    (1) sys.modules must not already have a cached "schema_validators"/
        "advisory_lock" from a prior load (source or target) -- handled by
        popping them below.
    (2) sys.path must put THIS lib_dir ahead of any OTHER copy of those
        plain-named files. This is the part a plain `if str(lib_dir) not in
        sys.path: sys.path.insert(0, ...)` (which is exactly what
        taskcard_store.py's OWN top-level code does) gets wrong here: other
        test files in this same pytest session (test_taskcard_store.py,
        test_advisory_lock.py, etc.) already inserted THIS repo's lib_dir
        into sys.path at collection time, at whatever position -- so when
        source's fixture runs first and freshly inserts source's lib_dir at
        position 0, target's later self-registration sees its own dir is
        "already present" (just not first) and skips re-inserting,
        leaving source's dir ahead of it in the search order. Force this
        lib_dir to the front unconditionally, removing any existing
        occurrence first, so it always wins regardless of what earlier
        test collection already did to sys.path.
    """
    for dep in _TASKCARD_STORE_PLAIN_DEPS:
        sys.modules.pop(dep, None)
    lib_dir_str = str(lib_dir)
    while lib_dir_str in sys.path:
        sys.path.remove(lib_dir_str)
    sys.path.insert(0, lib_dir_str)
    return _load_module(name, lib_dir / "taskcard_store.py")


@pytest.fixture
def source_taskcard_store(_isolated_sys_path):
    lib_dir = Path(SOURCE_REPO_PATH) / "scripts" / "pipeline" / "lib"
    if not (lib_dir / "taskcard_store.py").is_file():
        pytest.skip("source taskcard_store.py not found")
    return _load_taskcard_store_fresh("source_taskcard_store", lib_dir)


@pytest.fixture
def target_taskcard_store(_isolated_sys_path):
    lib_dir = REPO_ROOT / "scripts" / "pipeline" / "lib"
    return _load_taskcard_store_fresh("target_taskcard_store", lib_dir)


def test_taskcard_store_cas_semantics_match_source(tmp_path, source_taskcard_store, target_taskcard_store):
    """Same scenario, both implementations: append, advance via CAS, then
    a stale-expectation retry must be rejected identically on both sides."""
    record = {
        "task_id": "T-1", "status": "TODO", "recorded_at": "t0",
        "recorded_by": "a", "evidence_refs": [],
    }
    for mod, subdir in ((source_taskcard_store, "source"), (target_taskcard_store, "target")):
        store = mod.TaskcardStore("M-1", plan_state_dir=tmp_path / subdir)
        store.append(dict(record))
        store.update_taskcard_status("T-1", expected_status="TODO", new_status="READY", recorded_by="a")
        with pytest.raises(mod.TaskcardCASError):
            store.update_taskcard_status("T-1", expected_status="TODO", new_status="IN_PROGRESS", recorded_by="b")
        assert store.get("T-1")["status"] == "READY"


# --- Regression tests for the test-isolation bug found during implementation

def test_taskcard_store_fixtures_load_from_their_own_directory_not_each_others(
    source_taskcard_store, target_taskcard_store,
):
    """Direct proof of the fix: target's loaded module's OWN dependency
    (schema_validators) must resolve to a file under THIS repo, not
    aspose.org's -- and vice versa for source."""
    import inspect

    target_schema_validators = target_taskcard_store.validate_taskcard_record.__module__
    # __module__ alone doesn't carry the file path when loaded via
    # importlib with a synthetic name -- inspect the actual function's
    # __globals__['__file__'] instead, which does.
    target_file = inspect.getfile(target_taskcard_store.validate_taskcard_record)
    source_file = inspect.getfile(source_taskcard_store.validate_taskcard_record)
    assert "foss-launcher-skills-gitlab" in target_file.replace("\\", "/")
    assert "aspose.org" in source_file.replace("\\", "/") or SOURCE_REPO_PATH.replace("\\", "/") in source_file.replace("\\", "/")
    assert target_file != source_file


def test_isolated_sys_path_fixture_actually_restores_state():
    """Direct proof that _isolated_sys_path's cleanup fires, without
    depending on adjacent-test ordering (a test can't observe its OWN
    not-yet-run teardown from inside its own body, and pytest doesn't
    guarantee which test runs immediately before another) -- drive the
    fixture function as a plain generator instead."""
    gen = _isolated_sys_path.__wrapped__()
    path_before = list(sys.path)
    modules_before = set(sys.modules.keys())
    schema_validators_before = sys.modules.get("schema_validators")  # whatever this run's session already has
    next(gen)  # run setup half (snapshots current state)

    poison_path_entry = str(Path(SOURCE_REPO_PATH) / "scripts" / "pipeline" / "lib")
    sys.path.insert(0, poison_path_entry)
    poison_module = object()  # stand-in for a leaked/overwritten module
    sys.modules["schema_validators"] = poison_module

    with pytest.raises(StopIteration):
        next(gen)  # run teardown half (restores)

    assert sys.path == path_before
    assert poison_path_entry not in sys.path
    assert set(sys.modules.keys()) == modules_before
    # Restored to whatever it was BEFORE this test poisoned it -- not
    # unconditionally absent, since some other test in this same session
    # may legitimately already have a real "schema_validators" cached.
    assert sys.modules.get("schema_validators") is schema_validators_before
    assert sys.modules.get("schema_validators") is not poison_module
