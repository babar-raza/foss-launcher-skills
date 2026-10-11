def test_a_produced_file_carries_no_foreign_editing_language(produced):
    """Nothing the user writes should come out marked in another language."""
    pres = Presentation()
    pkg = produced(pres)

    with zipfile.ZipFile(pkg.path) as written:
        counts = _lang_counts(written)

    assert "ru-RU" not in counts, (
        "the saved file marks %d runs as ru-RU; languages present: %r"
        % (counts.get("ru-RU"), counts)
    )