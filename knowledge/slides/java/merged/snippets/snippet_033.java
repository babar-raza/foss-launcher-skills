@Test
    void openingADeckMustExposeTheLayoutsItContains() throws Exception {
        Path deck = Fixtures.authoredDeck(tempDir, "real.pptx", "First", "Second");

        long layoutPartsInFile;
        try (PptxPackage pkg = PptxPackage.open(deck)) {
            layoutPartsInFile = pkg.entryNames().stream()
                    .filter(name -> name.matches("ppt/slideLayouts/slideLayout\\d+\\.xml"))
                    .count();
        }
        assertThat(layoutPartsInFile)
                .as("the fixture must have several layouts for this test to mean anything")
                .isEqualTo(Fixtures.LAYOUTS_IN_FIXTURE);

        try (var pres = new Presentation(deck.toString())) {
            assertThat(pres.getLayoutSlides().size())
                    .as("layouts reported for a deck whose package contains %d of them",
                            layoutPartsInFile)
                    .isEqualTo((int) layoutPartsInFile);
        }
    }