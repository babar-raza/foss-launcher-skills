def test_preview_matrix_writes_png(tmp_path: Path):
    out = tmp_path / "matrix.png"
    result = run(
        "preview-matrix",
        ROBOTO,
        str(out),
        "--all-named",
        "--text",
        "Matrix QA",
    )
    assert result.returncode == 0
    assert out.exists()
    assert out.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert "Saved:" in result.stdout