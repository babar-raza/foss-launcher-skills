def test_a_produced_file_carries_no_placeholder_thumbnail(produced):
    """Shipping the template's preview as the document's own is a false claim."""
    pres = Presentation()
    pres.slides[0].shapes  # touch the deck so it is not a bare copy
    pkg = produced(pres)

    thumbnails = [n for n in pkg.namelist if n.startswith("docProps/thumbnail")]
    assert not thumbnails, (
        "the template's placeholder thumbnail is shipped in the output: %r"
        % thumbnails
    )