def test_preview_animation_path_showcase_writes_assets(tmp_path: Path):
    out = tmp_path / "animation-showcase"
    result = run(
        "preview-animation-path-showcase",
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
        "Anim Showcase",
    )
    assert result.returncode == 0
    assert (out / "roboto-animation-path.png").exists()
    assert (out / "roboto-animation-path-showcase.html").exists()
    assert (out / "roboto-animation-path-showcase-manifest.json").exists()
    assert (out / "roboto-animation-path-storyboard.html").exists()
    payload = json.loads((out / "roboto-animation-path-showcase-manifest.json").read_text(encoding="utf-8"))
    assert payload["type"] == "animation-showcase-package"
    assert payload["animation"]["filename"] == "roboto-animation-path.png"
    assert "Saved:" in result.stdout