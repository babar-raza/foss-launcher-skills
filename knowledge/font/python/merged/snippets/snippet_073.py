def test_preview_batch_can_write_svg_files(tmp_path: Path):
    out_dir = tmp_path / "preview-batch-svg"
    result = run(
        "preview-batch",
        ROBOTO,
        str(out_dir),
        "--instance-name",
        "Bold",
        "--format",
        "svg",
    )
    assert result.returncode == 0
    files = sorted(path.name for path in out_dir.glob("*.svg"))
    assert files == ["roboto-instance-bold.svg"]
    assert (out_dir / "roboto-instance-bold.svg").read_bytes().startswith(
        b'<?xml version="1.0" encoding="UTF-8"?>'
    )