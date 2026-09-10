def test_an_unimplemented_format_refuses_rather_than_writing_a_pptx(
    tmp_path, save_format
):
    """A format with no exporter must raise, never write a mislabelled package.

    This is the half of the behaviour that is already correct; it is asserted
    so a future change that adds a content type cannot quietly start writing
    presentation packages under a `.pdf` name instead.
    """
    pres = Presentation()
    try:
        with pytest.raises(ValueError):
            pres.save(str(tmp_path / ("out." + save_format.value.lower())), save_format)
    finally:
        pres.dispose()