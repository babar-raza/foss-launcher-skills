def test_preview_family_export_requires_instance_selection(tmp_path: Path):
    out_dir = tmp_path / "family-export"
    result = run("preview-family-export", ROBOTO, str(out_dir))
    assert result.returncode == 1
    assert "requires --all-named, --include-default, or at least one --instance-name" in result.stderr