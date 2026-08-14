def test_qa_report_package_output_writes_artifacts(tmp_path: Path):
    package_dir = tmp_path / "qa-package"
    result = run(
        "qa-report",
        ROBOTO,
        "--preset",
        "latin",
        "--text",
        "QA",
        "--preview-text",
        "Roboto QA",
        "--preview-instance-name",
        "Bold",
        "--package-output",
        str(package_dir),
    )

    assert result.returncode == 0
    assert "QA report:" in result.stdout
    assert f"Package: {package_dir}" in result.stdout
    assert (package_dir / "qa-report.json").exists()
    assert (package_dir / "qa-report.html").exists()
    assert (package_dir / "preview.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")

    payload = json.loads((package_dir / "qa-report.json").read_text(encoding="utf-8"))
    assert [item["kind"] for item in payload["artifacts"]] == ["json", "html", "preview"]
    html = (package_dir / "qa-report.html").read_text(encoding="utf-8")
    assert 'src="preview.png"' in html
    assert 'href="qa-report.json"' in html