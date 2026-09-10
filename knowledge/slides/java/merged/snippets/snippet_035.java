@Test
    void aSlideMustReportTheLayoutItIsRelatedTo() throws Exception {
        Path deck = Fixtures.authoredDeck(tempDir, "real.pptx", "First");

        String layoutNameInFile;
        try (PptxPackage pkg = PptxPackage.open(deck)) {
            String target = PackageAssertions.selectNodes(pkg,
                            "ppt/slides/_rels/slide1.xml.rels",
                            "//rel:Relationship[contains(@Type,'slideLayout')]").get(0)
                    .getAttribute("Target");
            String layoutPart = PptxPackage.resolveTarget("ppt/slides/slide1.xml", target);
            layoutNameInFile = PackageAssertions
                    .selectNodes(pkg, layoutPart, "//p:cSld").get(0).getAttribute("name");
        }
        assertThat(layoutNameInFile)
                .as("the fixture's layout must be named for this test to mean anything")
                .isNotEmpty();

        try (var pres = new Presentation(deck.toString())) {
            assertThat(pres.getSlides().get(0).getLayoutSlide().getName())
                    .as("layout name reported for a slide related to a layout named '%s'",
                            layoutNameInFile)
                    .isEqualTo(layoutNameInFile);
        }
    }