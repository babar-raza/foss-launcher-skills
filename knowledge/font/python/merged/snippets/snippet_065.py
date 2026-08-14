def test_preview_animation_path_review_writes_assets(tmp_path: Path):
    out = tmp_path / "animation-review"
    result = run(
        "preview-animation-path-review",
        ROBOTO,
        str(out),
        "--state",
        "Regular",
        "--state",
        "wght=700,wdth=75",
        "--state",
        "Bold",
        "--frames-per-segment",
        "3",
        "--preset",
        "draft",
        "--caption-mode",
        "both",
        "--text",
        "Anim Review",
    )
    assert result.returncode == 0
    assert (out / "roboto-animation-path-storyboard.md").exists()
    assert (out / "roboto-animation-path-storyboard.html").exists()
    assert (out / "roboto-animation-path-storyboard-manifest.json").exists()
    payload = json.loads((out / "roboto-animation-path-storyboard-manifest.json").read_text(encoding="utf-8"))
    assert payload["type"] == "animation-review-package"
    assert "Saved:" in result.stdout