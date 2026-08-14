def test_var_compat_json_output():
    result = run(
        "var-compat",
        ROBOTO,
        "--before-instance-name",
        "Regular",
        "--after-instance-name",
        "Condensed Bold",
        "--text",
        "Aspose",
        "--json",
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["before_label"] == "Regular"
    assert payload["after_label"] == "Condensed Bold"
    assert payload["is_compatible"] is True
    assert payload["issues"] == []
    assert payload["interpolation_issue_count"] >= 1
    assert payload["interpolation_issues"][0]["reason"] == "variation tuples became active"