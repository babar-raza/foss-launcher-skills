def test_preview_compare_writes_comparison_png(tmp_path: Path):
    out = tmp_path / "compare-sheet.png"
    result = run(
        "preview-compare",
        ROBOTO,
        str(out),
        "--before-instance-name",
        "Regular",
        "--after-instance-name",
        "Condensed Bold",
    )
    assert result.returncode == 0
    assert out.exists()
    assert out.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert "Saved:" in result.stdout