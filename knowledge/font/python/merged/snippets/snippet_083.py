def test_preview_compare_invalid_axis_exits_1(tmp_path: Path):
    out = tmp_path / "bad-compare-sheet.png"
    result = run(
        "preview-compare",
        ROBOTO,
        str(out),
        "--after-instance",
        "opsz=12",
    )
    assert result.returncode == 1
    assert "Unknown variable axis" in result.stderr