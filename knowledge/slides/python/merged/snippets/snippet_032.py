def test_the_document_summary_reports_the_real_slide_count(produced):
    """`docProps/app.xml` must be regenerated on save, not copied."""
    pres = Presentation()
    pres.slides.add_empty_slide(pres.layout_slides[0])
    pres.slides.add_empty_slide(pres.layout_slides[0])
    expected = len(pres.slides)
    pkg = produced(pres)

    declared = int(pkg.find_one("docProps/app.xml", "//*[local-name()='Slides']").text)
    in_package = len(pkg.findall("ppt/presentation.xml", "//p:sldIdLst/p:sldId"))

    assert in_package == expected, (
        "the package itself has %d slides, expected %d" % (in_package, expected)
    )
    assert declared == expected, (
        "docProps/app.xml reports <Slides>%d</Slides> for a %d-slide deck"
        % (declared, expected)
    )