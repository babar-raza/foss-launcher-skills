def test_preview_waterfall_requires_instance_selection(tmp_path: Path):
    out = tmp_path / "waterfall.png"
    result = run("preview-waterfall", ROBOTO, str(out))
    assert result.returncode == 1
    assert "requires --all-named, --include-default, or at least one --instance-name" in result.stderr