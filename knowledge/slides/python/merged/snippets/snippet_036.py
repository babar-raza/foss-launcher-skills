def test_the_saved_file_declares_the_format_that_was_asked_for(produced, save_format):
    """The main part's content type must match the requested format."""
    pkg = produced(
        Presentation(), save_format, "deck." + EXTENSION[save_format]
    )

    assert pkg.content_type_of("ppt/presentation.xml") == MAIN_PART_CONTENT_TYPE[save_format]