def test_preview_family_export_writes_review_pack(tmp_path: Path):
    out_dir = tmp_path / "family-export"
    result = run(
        "preview-family-export",
        ROBOTO,
        str(out_dir),
        "--instance-name",
        "Bold",
        "--include-default",
        "--family-name",
        "Roboto Release",
        "--text",
        "Release Notes",
    )
    assert result.returncode == 0
    assert (out_dir / "family-review-board.png").exists()
    assert (out_dir / "family-waterfall.png").exists()
    assert (out_dir / "family-matrix.png").exists()
    assert (out_dir / "family-review-board.md").exists()
    assert (out_dir / "family-review-board.html").exists()
    manifest = json.loads((out_dir / "family-review-board-manifest.json").read_text(encoding="utf-8"))
    assert manifest["kind"] == "family_review_export"
    assert manifest["family_name"] == "Roboto Release"
    assert manifest["bundle_count"] == 2
    assert "Family review export: Roboto Release" in result.stdout