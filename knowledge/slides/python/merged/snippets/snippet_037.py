def test_the_six_office_formats_do_not_all_produce_the_same_file(produced, tmp_path):
    """Six requested formats must not collapse into one content type."""
    written = {}
    for save_format, extension in EXTENSION.items():
        pkg = produced(Presentation(), save_format, "distinct." + extension)
        written[save_format] = pkg.content_type_of("ppt/presentation.xml")

    assert len(set(written.values())) == len(written), (
        "the six formats produced %d distinct main content types, not %d: %r"
        % (len(set(written.values())), len(written),
           {f.value: t for f, t in written.items()})
    )