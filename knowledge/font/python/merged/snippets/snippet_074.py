def test_preview_batch_requires_selection(tmp_path: Path):
    out_dir = tmp_path / "preview-batch-none"
    result = run("preview-batch", ROBOTO, str(out_dir))
    assert result.returncode == 1
    assert "requires --all-named or at least one --instance-name" in result.stderr