def test_var_compat_json_output_file(tmp_path: Path):
    out = tmp_path / "compat.json"
    result = run(
        "var-compat",
        ROBOTO,
        "--before-instance-name",
        "Regular",
        "--after-instance-name",
        "Condensed Bold",
        "--text",
        "Aspose",
        "--json-output",
        str(out),
    )
    assert result.returncode == 0
    assert "Compatible:" in result.stdout
    assert "Saved JSON:" in result.stdout
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["before_label"] == "Regular"
    assert payload["after_label"] == "Condensed Bold"
    assert payload["is_compatible"] is True