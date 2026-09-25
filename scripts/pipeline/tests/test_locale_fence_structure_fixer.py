"""Tests for commands/governance/locale_fence_structure_fixer.py (TC-09,
MT073-2026-09-24-LOCALE-CODE-BLOCK-DEFECT-REMEDIATION).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
_LIB_DIR = str(_HERE / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
_GOV_DIR = str(_HERE / "commands" / "governance")
if _GOV_DIR not in sys.path:
    sys.path.insert(0, _GOV_DIR)

import locale_fence_structure_fixer as cli  # noqa: E402

_EN = """---
title: X
---

## Setup

```csharp
using Aspose.ThreeD;

var scene = new Scene();
```
"""

_LOC_MISSING_OPENER = """---
title: Y
---

## Instellen

var scene = new Scene();
```
"""


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")


def _init_repo(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=T", "commit", "-q", "-m", "init"],
        cwd=tmp_path, check=True,
    )


def _make_bucket3_repo(tmp_path: Path) -> None:
    """One page, one locale with a real missing_opener defect, one other
    locale that's already correct -- so the finding's fan-out is 1 (Bucket
    3's own low-fan-out definition)."""
    _write(tmp_path / "content/docs.aspose.org/en/3d/net/installation.md", _EN)
    _write(tmp_path / "content/docs.aspose.org/de/3d/net/installation.md", _LOC_MISSING_OPENER)
    _write(tmp_path / "content/docs.aspose.org/fr/3d/net/installation.md", _EN.replace("## Setup", "## Installation"))
    _init_repo(tmp_path)


def test_find_bucket3_pairs_detects_low_fanout_group(tmp_path):
    _make_bucket3_repo(tmp_path)
    pairs = cli.find_bucket3_pairs(repo_root=tmp_path)
    assert pairs == [("content/docs.aspose.org/en/3d/net/installation.md", "content/docs.aspose.org/de/3d/net/installation.md")]


def test_main_dry_run_does_not_write(tmp_path):
    _make_bucket3_repo(tmp_path)
    report_path = tmp_path / "report.json"
    de_path = tmp_path / "content/docs.aspose.org/de/3d/net/installation.md"
    before = de_path.read_bytes()

    rc = cli.main(["--repo-root", str(tmp_path), "--report", str(report_path)])
    assert rc == 0
    assert de_path.read_bytes() == before

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["mode"] == "dry-run"
    assert report["applied_count"] == 0
    assert report["status_counts"].get("ok") == 1


def test_main_apply_writes_verified_repair(tmp_path):
    _make_bucket3_repo(tmp_path)
    de_path = tmp_path / "content/docs.aspose.org/de/3d/net/installation.md"

    rc = cli.main(["--repo-root", str(tmp_path), "--apply"])
    assert rc == 0
    new_content = de_path.read_text(encoding="utf-8")
    assert "```csharp\nusing Aspose.ThreeD;" in new_content
    assert "## Instellen" in new_content  # translated heading preserved


def test_main_never_writes_unresolved_files(tmp_path):
    """A locale whose real defect isn't either known fence-structure
    signature must be left completely untouched, even under --apply."""
    _write(tmp_path / "content/docs.aspose.org/en/3d/net/installation.md", _EN)
    _write(
        tmp_path / "content/docs.aspose.org/de/3d/net/installation.md",
        _EN.replace("var scene = new Scene();", "var scene = TOTALLY_DIFFERENT_CODE();"),
    )
    _write(tmp_path / "content/docs.aspose.org/fr/3d/net/installation.md", _EN.replace("## Setup", "## Installation"))
    _init_repo(tmp_path)
    de_path = tmp_path / "content/docs.aspose.org/de/3d/net/installation.md"
    before = de_path.read_bytes()

    rc = cli.main(["--repo-root", str(tmp_path), "--apply"])
    assert rc == 0
    assert de_path.read_bytes() == before
