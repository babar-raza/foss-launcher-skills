def test_preview_family_board_writes_png(tmp_path: Path):
    out = tmp_path / "family-review-board.png"
    result = run(
        "preview-family-board",
        ROBOTO,
        str(out),
        "--instance-name",
        "Bold",
        "--instance-name",
        "Condensed Bold",
        "--include-default",
        "--family-name",
        "Roboto Review",
        "--text",
        "Review Board",
    )
    assert result.returncode == 0
    assert out.exists()
    assert out.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert "Saved:" in result.stdout