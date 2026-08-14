def test_preview_family_board_requires_instance_selection(tmp_path: Path):
    out = tmp_path / "family-review-board.png"
    result = run("preview-family-board", ROBOTO, str(out))
    assert result.returncode == 1
    assert "requires --all-named, --include-default, or at least one --instance-name" in result.stderr