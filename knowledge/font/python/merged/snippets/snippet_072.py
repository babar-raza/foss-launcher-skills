def test_preview_batch_selected_names_and_default(tmp_path: Path):
    out_dir = tmp_path / "preview-batch-selected"
    result = run(
        "preview-batch",
        ROBOTO,
        str(out_dir),
        "--instance-name",
        "Bold",
        "--include-default",
    )
    assert result.returncode == 0
    files = sorted(path.name for path in out_dir.glob("*.png"))
    assert files == ["roboto-instance-bold.png", "roboto-instance-regular.png"]