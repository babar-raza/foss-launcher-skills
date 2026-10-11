def test_the_document_summary_follows_a_removal(produced):
    """Removing a slide must be reflected in the summary too."""
    pres = Presentation()
    pres.slides.add_empty_slide(pres.layout_slides[0])
    pres.slides.add_empty_slide(pres.layout_slides[0])
    pres.slides.remove_at(1)
    expected = len(pres.slides)
    pkg = produced(pres)

    declared = int(pkg.find_one("docProps/app.xml", "//*[local-name()='Slides']").text)
    assert declared == expected, (
        "docProps/app.xml reports <Slides>%d</Slides> for a %d-slide deck"
        % (declared, expected)
    )