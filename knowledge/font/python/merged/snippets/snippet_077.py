def test_preview_grid_can_write_svg_files(tmp_path: Path):
    out_dir = tmp_path / "preview-grid-svg"
    result = run(
        "preview-grid",
        ROBOTO,
        str(out_dir),
        "--axis",
        "wght",
        "--value",
        "400",
        "--value",
        "700",
        "--format",
        "svg",
    )
    assert result.returncode == 0
    files = sorted(path.name for path in out_dir.glob("*.svg"))
    assert len(files) == 2
    assert any(name.endswith(".svg") for name in files)