def test_var_delta_json_output():
    result = run(
        "var-delta",
        ROBOTO,
        "--instance-name",
        "Condensed Bold",
        "--codepoint",
        "0x41",
        "--top-points",
        "1",
        "--json",
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["codepoint"] == 0x41
    assert payload["instance_label"] == "Condensed Bold"
    assert payload["active_tuple_count"] >= 1
    assert payload["strongest_points"]
    assert "referenced_outline_points" in payload["active_tuples"][0]
    assert "referenced_phantom_points" in payload["active_tuples"][0]
    assert len(payload["active_tuples"][0]["top_points"]) <= 1