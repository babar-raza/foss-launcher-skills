def test_a_saved_file_reports_when_it_was_saved(produced):
    """`dcterms:modified` must be the time of this save, not the template's.

    Left alone it is whatever `docProps/core.xml` was copied with, so every
    file the library ever wrote claimed to have been last modified when the
    bundled template was built — years before the user's own work, and a
    plausible-looking date rather than an obviously missing one.
    """
    before = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    pkg = produced(Presentation())

    element = pkg.find_one(
        "docProps/core.xml", "//*[local-name()='modified']"
    )
    stamped = datetime.datetime.strptime(element.text, "%Y-%m-%dT%H:%M:%SZ")

    assert stamped >= before - datetime.timedelta(seconds=2), (
        "dcterms:modified is %s, which is not this save; the file was written "
        "at %s and is reporting the template's build time instead"
        % (element.text, before.isoformat())
    )
    assert stamped <= before + datetime.timedelta(minutes=5), (
        "dcterms:modified is %s, in the future relative to the save at %s"
        % (element.text, before.isoformat())
    )