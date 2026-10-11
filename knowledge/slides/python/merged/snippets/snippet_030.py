def test_the_bundled_template_carries_no_foreign_editing_language():
    """The template must not stamp a language the user did not choose."""
    with zipfile.ZipFile(TEMPLATE) as template:
        counts = _lang_counts(template)

    assert "ru-RU" not in counts, (
        "the bundled template marks %d runs as ru-RU; every produced file "
        "inherits them. languages in the template: %r" % (counts.get("ru-RU"), counts)
    )