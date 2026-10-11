def test_preview_animation_path_requires_two_states(tmp_path: Path):
    out = tmp_path / "bad-animation-path.png"
    result = run(
        "preview-animation-path",
        ROBOTO,
        str(out),
        "--state",
        "Bold",
    )
    assert result.returncode == 1
    assert "at least two steps" in result.stderr