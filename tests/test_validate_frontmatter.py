import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.pipeline.commands.content.validate_frontmatter import validate_text  # noqa: E402


def test_duplicate_key_detected():
    text = "---\ntitle: One\ntitle: Two\n---\n\nBody\n"
    findings = validate_text(text, "content/docs.aspose.org/en/words/python/page.md")
    assert any(f.check == "duplicate_key" and "title" in f.detail for f in findings)


def test_double_frontmatter_detected():
    text = "---\ntitle: One\n---\n\n---\nlayout: page\n---\n\nBody\n"
    findings = validate_text(text, "content/docs.aspose.org/en/words/python/page.md")
    assert any(f.check == "double_frontmatter" for f in findings)


def test_blog_evidence_requires_draft_claims_and_apis():
    text = "---\ntitle: Blog\nevidence:\n  claims: []\n  apis: []\n---\n\nBody\n"
    findings = validate_text(text, "content/blog.aspose.org/words/python/my-post/index.md")
    details = "\n".join(f.detail for f in findings)
    assert "draft" in details
    assert "claims" in details
    assert "apis" in details


def test_blog_locale_file_exempt():
    text = "---\ntitle: Blog\n---\n\nBody\n"
    findings = validate_text(text, "content/blog.aspose.org/words/python/my-post/index.fr.md")
    assert findings == []


def test_cli_json_output(tmp_path):
    page = tmp_path / "page.md"
    page.write_text("---\ntitle: One\ntitle: Two\n---\n\nBody\n", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "pipeline" / "commands" / "content" / "validate_frontmatter.py"),
            str(page),
            "--json",
        ],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data[0]["check"] == "duplicate_key"
