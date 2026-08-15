from pathlib import Path

import yaml

from commands.ops import translation_coverage as coverage


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _manifest(repo: Path, source_hash: str) -> dict:
    return {
        "schema_version": 1,
        "campaign_id": "fixture",
        "validation_policy": "zero-defect",
        "target_locales": ["es", "fr"],
        "expected_source_count": 1,
        "expected_output_count": 2,
        "sources": [
            {
                "site_id": "docs.aspose.org",
                "family": "words",
                "platform": "net",
                "source_path": "content/docs.aspose.org/en/words/net/page.md",
                "source_sha256": source_hash,
                "outputs": {
                    "es": "content/docs.aspose.org/es/words/net/page.md",
                    "fr": "content/docs.aspose.org/fr/words/net/page.md",
                },
                "wave": 2,
            }
        ],
    }


def test_campaign_scan_passes_exact_complete_matrix(tmp_path):
    source = tmp_path / "content/docs.aspose.org/en/words/net/page.md"
    es = tmp_path / "content/docs.aspose.org/es/words/net/page.md"
    fr = tmp_path / "content/docs.aspose.org/fr/words/net/page.md"
    _write(source, "---\ntitle: Hello\ndescription: English page\n---\nBody\n")
    _write(es, "---\ntitle: Hola\ndescription: Pagina espanola\n---\nCuerpo\n")
    _write(fr, "---\ntitle: Bonjour\ndescription: Page francaise\n---\nCorps\n")
    _write(
        tmp_path / "configs/docs.aspose.org.toml",
        "[languages.en]\n[languages.es]\n[languages.fr]\n",
    )
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(
        yaml.safe_dump(_manifest(tmp_path, coverage._sha256(source))),
        encoding="utf-8",
    )

    result = coverage.scan_campaign_manifest(manifest_path, tmp_path)

    assert result["passed"] is True
    assert result["present_outputs"] == 2


def test_campaign_scan_fails_missing_fallback_unexpected_and_unserved(tmp_path):
    source = tmp_path / "content/docs.aspose.org/en/words/net/page.md"
    es = tmp_path / "content/docs.aspose.org/es/words/net/page.md"
    extra = tmp_path / "content/docs.aspose.org/es/words/net/extra.md"
    source_text = "---\ntitle: Hello\ndescription: English page\n---\nBody\n"
    _write(source, source_text)
    _write(es, source_text)
    _write(extra, "---\ntitle: Extra\n---\nExtra\n")
    _write(
        tmp_path / "configs/docs.aspose.org.toml",
        "[languages.en]\n[languages.es]\n",
    )
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(
        yaml.safe_dump(_manifest(tmp_path, coverage._sha256(source))),
        encoding="utf-8",
    )

    result = coverage.scan_campaign_manifest(manifest_path, tmp_path)

    assert result["passed"] is False
    assert result["missing"] == [
        "content/docs.aspose.org/fr/words/net/page.md"
    ]
    assert result["fallbacks"] == [
        "content/docs.aspose.org/es/words/net/page.md"
    ]
    assert result["unexpected"] == [
        "content/docs.aspose.org/es/words/net/extra.md"
    ]
    assert result["unserved"] == [
        {"site_id": "docs.aspose.org", "locale": "fr"}
    ]
