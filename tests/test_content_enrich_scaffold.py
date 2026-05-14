import json
import subprocess
import sys
from pathlib import Path

from scripts.pipeline.commands.enrichment.content_enrich import run

REPO_ROOT = Path(__file__).resolve().parent.parent


def _fixture(tmp_path):
    knowledge = tmp_path / "knowledge"
    merged = knowledge / "words" / "python" / "merged"
    merged.mkdir(parents=True)
    (merged / "claims.json").write_text(
        json.dumps([
            {"claim_id": "CLM-1", "kind": "feature", "category": "conversion"},
            {"claim_id": "CLM-2", "kind": "api", "category": "metadata"},
        ]),
        encoding="utf-8",
    )
    content = tmp_path / "content"
    docs = content / "docs.aspose.org" / "en" / "words" / "python"
    docs.mkdir(parents=True)
    (docs / "intro.md").write_text("---\ntitle: Intro\n---\n", encoding="utf-8")
    return knowledge, content


def test_audit_writes_coverage_matrix(tmp_path):
    knowledge, content = _fixture(tmp_path)
    output = tmp_path / "reports"

    result = run("words", "python", output_root=output, knowledge_root=knowledge, content_root=content)

    assert result["audit"]["cluster_count"] == 2
    assert (output / "words" / "python" / "coverage-matrix.json").exists()


def test_dry_run_writes_candidate_and_handoff_manifests(tmp_path):
    knowledge, content = _fixture(tmp_path)
    output = tmp_path / "reports"

    result = run("words", "python", mode="dry-run", output_root=output, knowledge_root=knowledge, content_root=content)

    out_dir = output / "words" / "python"
    assert result["candidates"]["denominator"]["valid"] is True
    assert (out_dir / "candidate-list.json").exists()
    assert (out_dir / "handoff-manifest.json").exists()


def test_cli_execute_does_not_write_content(tmp_path):
    knowledge, content = _fixture(tmp_path)
    output = tmp_path / "reports"

    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "pipeline" / "commands" / "enrichment" / "content_enrich.py"),
            "words",
            "python",
            "--mode",
            "execute",
            "--output-root",
            str(output),
            "--knowledge-root",
            str(knowledge),
            "--content-root",
            str(content),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert (output / "words" / "python" / "handoff-manifest.json").exists()
    assert len(list(content.rglob("*.md"))) == 1
