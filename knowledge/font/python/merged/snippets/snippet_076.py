def test_preview_grid_requires_primary_values(tmp_path: Path):
    out_dir = tmp_path / "preview-grid-none"
    result = run("preview-grid", ROBOTO, str(out_dir), "--axis", "wght")
    assert result.returncode == 1
    assert "requires at least one value" in result.stderr