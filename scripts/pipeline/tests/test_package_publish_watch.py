"""
Tests for commands/ops/package_publish_watch.py (Mission
MT015-2026-07-30-PACKAGE-REGISTRY, TC-MT015-09).

Multi-registry sibling of publish_watcher.py (Maven-only). Covers the
debounce-gated proposal flow for pypi/nuget/npm/go_modules/cargo, the
counter-persists-but-flip-doesn't design (see module docstring), and the
content-healing-needed hint surfaced per proposal.
"""

import json
import sys
from pathlib import Path

import pytest

_PIPELINE_ROOT = Path(__file__).resolve().parents[1]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

import commands.ops.package_publish_watch as sut
from package_registries import CheckResult


@pytest.fixture(autouse=True)
def isolate_repo(tmp_path):
    data_path = tmp_path / "package_registry.json"
    empty_content_root = tmp_path / "content"
    empty_content_root.mkdir()
    sut.configure(data_path=data_path, content_root=empty_content_root)
    yield data_path
    sut.configure(data_path=None, content_root=None)


def _fake_adapter(result: CheckResult):
    class _Adapter:
        @staticmethod
        def check_published(candidate):
            return result
    return _Adapter()


def _entry(registry_type="pypi", published=False, consecutive=0):
    return {
        "registry_type": registry_type,
        "candidate": {"name": "aspose-cells-foss"},
        "verification": {"published": published, "consecutive_checks_agreeing": consecutive},
    }


def test_first_published_check_increments_counter_but_no_proposal():
    data = {"cells": {"python": _entry(consecutive=0)}}
    result = CheckResult(published=True, ambiguous=False, evidence_url="u", method="m")
    adapters = {"pypi": _fake_adapter(result)}
    proposals = sut.check_unpublished_entries(data, adapters=adapters)
    assert proposals == []
    assert data["cells"]["python"]["verification"]["consecutive_checks_agreeing"] == 1
    assert data["cells"]["python"]["verification"]["published"] is False  # never auto-flipped


def test_second_consecutive_published_check_produces_proposal():
    data = {"cells": {"python": _entry(consecutive=1)}}
    result = CheckResult(published=True, ambiguous=False, evidence_url="https://pypi.org/x", method="pypi-json-api", verified_owner="Aspose")
    adapters = {"pypi": _fake_adapter(result)}
    proposals = sut.check_unpublished_entries(data, adapters=adapters)
    assert len(proposals) == 1
    p = proposals[0]
    assert p["family"] == "cells" and p["platform"] == "python"
    assert p["evidence_url"] == "https://pypi.org/x"
    assert p["verified_owner"] == "Aspose"
    # counter is NOT required to persist a specific value post-flip; published flip itself must NOT be applied
    assert data["cells"]["python"]["verification"]["published"] is False


def test_ambiguous_result_does_not_advance_counter():
    data = {"cells": {"python": _entry(consecutive=1)}}
    result = CheckResult(published=False, ambiguous=True, evidence_url="u", method="m")
    adapters = {"pypi": _fake_adapter(result)}
    proposals = sut.check_unpublished_entries(data, adapters=adapters)
    assert proposals == []
    assert data["cells"]["python"]["verification"]["consecutive_checks_agreeing"] == 1  # unchanged


def test_not_published_result_resets_counter():
    data = {"cells": {"python": _entry(consecutive=1)}}
    result = CheckResult(published=False, ambiguous=False, evidence_url="u", method="m")
    adapters = {"pypi": _fake_adapter(result)}
    sut.check_unpublished_entries(data, adapters=adapters)
    assert data["cells"]["python"]["verification"]["consecutive_checks_agreeing"] == 0


def test_already_published_entries_are_never_rechecked():
    data = {"cells": {"python": _entry(published=True)}}
    calls = []

    class _Adapter:
        @staticmethod
        def check_published(candidate):
            calls.append(candidate)
            return CheckResult(published=True, ambiguous=False, evidence_url="u", method="m")

    sut.check_unpublished_entries(data, adapters={"pypi": _Adapter()})
    assert calls == []


def test_maven_entries_are_skipped_own_watcher_handles_them():
    data = {"cells": {"java": _entry(registry_type="maven", consecutive=1)}}
    proposals = sut.check_unpublished_entries(data, adapters={"pypi": _fake_adapter(
        CheckResult(published=True, ambiguous=False, evidence_url="u", method="m"))})
    assert proposals == []
    # counter untouched -- no adapter registered for "maven" in this watcher
    assert data["cells"]["java"]["verification"]["consecutive_checks_agreeing"] == 1


def test_apply_proposal_flips_state_correctly():
    data = {"cells": {"python": _entry(consecutive=2)}}
    proposal = {
        "family": "cells", "platform": "python",
        "candidate": {"name": "aspose-cells-foss"},
        "evidence_url": "https://pypi.org/x", "method": "pypi-json-api", "verified_owner": "Aspose",
    }
    sut.apply_proposal(data, proposal, checked_at="2026-08-01")
    entry = data["cells"]["python"]
    assert entry["verification"]["published"] is True
    assert entry["verification"]["verified_at"] == "2026-08-01"
    assert entry["verification"]["verified_owner"] == "Aspose"


def test_apply_proposal_is_not_called_by_run_watch(tmp_path):
    """Design invariant (matches test_publish_watcher.py's own test of the
    same name): the automatic path never writes verification.published --
    proven observationally (state stays False) rather than by monkeypatching
    apply_proposal itself."""
    data_path = tmp_path / "package_registry.json"
    original = {"cells": {"python": _entry(consecutive=1)}}
    data_path.write_text(json.dumps(original), encoding="utf-8")
    sut.configure(data_path=data_path)

    result = CheckResult(published=True, ambiguous=False, evidence_url="u", method="m")
    sut.run_watch(adapters={"pypi": _fake_adapter(result)})

    assert json.loads(data_path.read_text(encoding="utf-8"))["cells"]["python"]["verification"]["published"] is False


def test_format_issue_body_includes_actionable_steps_and_healing_hint():
    proposals = [{
        "family": "cells", "platform": "python", "registry_type": "pypi",
        "evidence_url": "https://pypi.org/x", "content_healing_needed": True,
        "literal_content_files_flagged": 5,
    }]
    body = sut.format_issue_body(proposals)
    assert "Action Required" in body
    assert "cells/python" in body
    assert "content healing needed, 5 file(s)" in body


def test_format_issue_body_no_healing_needed_case():
    proposals = [{
        "family": "cells", "platform": "python", "registry_type": "pypi",
        "evidence_url": "https://pypi.org/x", "content_healing_needed": False,
    }]
    body = sut.format_issue_body(proposals)
    assert "no literal content healing needed" in body


def test_cli_no_persist_flag_leaves_disk_untouched(tmp_path):
    """CLI-wiring test -- uses main()'s `adapters` test-injection point (zero
    live network calls) rather than monkeypatching run_watch itself."""
    data_path = tmp_path / "package_registry.json"
    original = {"cells": {"python": _entry(consecutive=0)}}
    data_path.write_text(json.dumps(original), encoding="utf-8")
    sut.configure(data_path=data_path)

    result = CheckResult(published=True, ambiguous=False, evidence_url="u", method="m")
    exit_code = sut.main(["--no-persist-counters"], adapters={"pypi": _fake_adapter(result)})
    assert exit_code == 0  # 1 agreeing check only advances the counter, doesn't reach threshold=2
    on_disk = json.loads(data_path.read_text(encoding="utf-8"))
    assert on_disk["cells"]["python"]["verification"]["consecutive_checks_agreeing"] == 0  # disk untouched


def test_cli_persists_updated_counters_by_default(tmp_path):
    data_path = tmp_path / "package_registry.json"
    data_path.write_text(json.dumps({"cells": {"python": _entry(consecutive=0)}}), encoding="utf-8")
    sut.configure(data_path=data_path)

    result = CheckResult(published=True, ambiguous=False, evidence_url="u", method="m")
    sut.main([], adapters={"pypi": _fake_adapter(result)})
    on_disk = json.loads(data_path.read_text(encoding="utf-8"))
    assert on_disk["cells"]["python"]["verification"]["consecutive_checks_agreeing"] == 1


def test_literal_content_scope_counts_flagged_files(tmp_path):
    """_literal_content_scope must use the configurable _CONTENT_ROOT (not the
    real repo content/), so this test runs in milliseconds against fixture
    files instead of scanning the full ~14k-file real corpus."""
    docs_dir = tmp_path / "content" / "docs.aspose.org" / "en" / "slides" / "net" / "getting-started"
    docs_dir.mkdir(parents=True)
    (docs_dir / "installation.md").write_text(
        "```bash\ndotnet add package Aspose.Slides.Foss\n```\n", encoding="utf-8"
    )
    clean_dir = tmp_path / "content" / "docs.aspose.org" / "en" / "slides" / "net" / "developer-guide"
    clean_dir.mkdir(parents=True)
    (clean_dir / "shapes.md").write_text("No install text here.\n", encoding="utf-8")

    sut.configure(data_path=tmp_path / "package_registry.json", content_root=tmp_path / "content")
    entry = {"registry_type": "nuget", "verification": {"published": False}}
    count = sut._literal_content_scope("slides", "net", entry)
    assert count == 1


def test_cli_exit_code_reflects_proposals(tmp_path):
    """Real proposal path, no monkeypatch: seed the counter at 1 (one prior
    agreeing check already recorded) so this run's 2nd agreeing result
    crosses the debounce threshold via main()'s real adapters-injection seam."""
    data_path = tmp_path / "package_registry.json"
    data_path.write_text(json.dumps({"cells": {"python": _entry(consecutive=1)}}), encoding="utf-8")
    sut.configure(data_path=data_path)

    result = CheckResult(published=True, ambiguous=False, evidence_url="u", method="m")
    exit_code = sut.main(["--no-persist-counters"], adapters={"pypi": _fake_adapter(result)})
    assert exit_code == 1
