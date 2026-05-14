import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.pipeline.commands.governance import skill_context  # noqa: E402


def test_begin_current_check_and_end(tmp_path):
    skill_context.configure(repo_root=tmp_path)
    try:
        assert skill_context.main(["begin", "--skill", "S-108", "--scope", "docs/**,reports/**"]) == 0
        active = tmp_path / "reports" / "skill-context" / "ACTIVE.json"
        assert active.exists()
        record = json.loads(active.read_text(encoding="utf-8"))
        assert record["skill_id"] == "S-108"
        assert skill_context.main(["current"]) == 0
        assert skill_context.main(["check", "--file", "docs/parity/example.md"]) == 0
        assert skill_context.main(["check", "--file", "content/page.md"]) == 1
        assert skill_context.main(["end", "--skill", "S-108", "--status", "completed"]) == 0
        assert not active.exists()
        assert list((tmp_path / "reports" / "skill-context" / "history").glob("*-S-108.json"))
    finally:
        skill_context.configure()


def test_current_without_context_returns_2(tmp_path):
    skill_context.configure(repo_root=tmp_path)
    try:
        assert skill_context.main(["current"]) == 2
    finally:
        skill_context.configure()


def test_gap_context_requires_existing_report(tmp_path):
    skill_context.configure(repo_root=tmp_path)
    try:
        assert skill_context.main(["gap", "--task", "demo", "--report", "missing.md"]) == 1
    finally:
        skill_context.configure()


def test_gap_context_uses_short_ttl(tmp_path):
    skill_context.configure(repo_root=tmp_path)
    try:
        report = tmp_path / "gap.md"
        report.write_text("gap", encoding="utf-8")
        assert skill_context.main(["gap", "--task", "demo", "--report", str(report), "--scope", "docs/**"]) == 0
        active = tmp_path / "reports" / "skill-context" / "ACTIVE.json"
        record = json.loads(active.read_text(encoding="utf-8"))
        old = datetime.now(tz=timezone.utc) - timedelta(minutes=31)
        record["started_at"] = old.isoformat().replace("+00:00", "Z")
        active.write_text(json.dumps(record), encoding="utf-8")
        assert skill_context.main(["current"]) == 2
        assert not active.exists()
        assert list((tmp_path / "reports" / "skill-context" / "history").glob("*-GAP-APPROVED.json"))
    finally:
        skill_context.configure()
