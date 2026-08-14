def test_info_rejects_collection_index_for_non_ttc():
    result = run("info", ROBOTO, "--collection-index", "1")
    assert result.returncode == 1
    assert "collection_index is only supported for TTC sources" in result.stderr