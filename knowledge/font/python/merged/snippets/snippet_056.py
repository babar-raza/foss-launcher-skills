def test_qa_report_writes_json_and_html(tmp_path: Path):
    json_output = tmp_path / "qa.json"
    html_output = tmp_path / "qa.html"
    result = run(
        "qa-report",
        ROBOTO,
        "--preset",
        "latin",
        "--text",
        "QA",
        "--codepoint",
        "0x10FFFF",
        "--json-output",
        str(json_output),
        "--html-output",
        str(html_output),
    )

    assert result.returncode == 0
    assert "QA report:" in result.stdout
    assert "Coverage:" in result.stdout
    payload = json.loads(json_output.read_text(encoding="utf-8"))
    assert payload["kind"] == "font_qa_report"
    assert payload["coverage"]["requested_presets"] == ["latin"]
    assert any(item["code"] == "missing-requested-codepoints" for item in payload["warnings"])
    html = html_output.read_text(encoding="utf-8")
    assert "Font QA Report" in html
    assert "Next Actions" in html