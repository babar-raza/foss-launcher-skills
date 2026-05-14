import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
GAP_SRC = REPO_ROOT / "scripts" / "gap-eval" / "src"


def _findings_file(tmp_path: Path) -> Path:
    path = tmp_path / "sample-python.json"
    path.write_text(
        json.dumps(
            {
                "findings": [
                    {
                        "id": "F-001",
                        "type": "wrong-package",
                        "severity": "S",
                        "file": "docs/page.md",
                        "old_value": "old.pkg",
                        "correct_value": "new.pkg",
                        "description": "Wrong package name",
                    },
                    {
                        "id": "F-002",
                        "type": "phantom-api",
                        "severity": "M",
                        "old_value": "MissingApi",
                        "description": "API is not real",
                    },
                    {
                        "id": "F-003",
                        "type": "wrong-claim",
                        "tier_resolved_by": 3,
                        "tier3_cache_hit": False,
                        "old_value": "false claim",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


def test_fix_spec_dry_run_generates_specs(tmp_path):
    findings = _findings_file(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            str(GAP_SRC / "fix_spec.py"),
            "sample",
            "python",
            "--findings-json",
            str(findings),
            "--output-root",
            str(tmp_path / "out"),
            "--dry-run",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["findings_count"] == 3
    assert payload["fix_specs"][0]["strategy"] == "auto"
    assert payload["fix_specs"][1]["strategy"] == "needs_operator_edit"


def test_fix_spec_writes_to_redirected_output_root(tmp_path):
    findings = _findings_file(tmp_path)
    output_root = tmp_path / "out"

    result = subprocess.run(
        [
            sys.executable,
            str(GAP_SRC / "fix_spec.py"),
            "sample",
            "python",
            "--findings-json",
            str(findings),
            "--output-root",
            str(output_root),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    specs_path = output_root / "agents" / "remediation" / "sample-python" / "fix_specs.json"
    plan_path = output_root / "agents" / "remediation" / "sample-python" / "plan.md"
    assert specs_path.exists()
    assert plan_path.exists()
    assert json.loads(specs_path.read_text(encoding="utf-8"))["findings_count"] == 3
    assert "Remediation Plan" in plan_path.read_text(encoding="utf-8")


def test_origin_map_dry_run_adds_origin_summary(tmp_path):
    findings = _findings_file(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            str(GAP_SRC / "origin_map.py"),
            str(findings),
            "sample",
            "python",
            "--no-grep",
            "--dry-run",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["origin_summary"]["total"] == 3
    assert payload["origin_summary"]["tier3_non_deterministic_count"] == 1
    assert payload["findings"][0]["repair_route"] == "S-46"


def test_synthesize_clusters_reports_without_network(tmp_path):
    reports = tmp_path / "gap-analysis"
    reports.mkdir()
    _findings_file(reports)

    result = subprocess.run(
        [
            sys.executable,
            str(GAP_SRC / "synthesize.py"),
            "--reports-dir",
            str(reports),
            "--output-root",
            str(tmp_path),
            "--dry-run",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["findings_count"] == 3
    assert payload["clusters"]["wrong-package"]["count"] == 1
