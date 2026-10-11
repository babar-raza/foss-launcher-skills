@Test
    void openingADeckMustExposeTheMasterItContains() throws Exception {
        Path deck = Fixtures.authoredDeck(tempDir, "real.pptx", "First");

        long masterPartsInFile;
        try (PptxPackage pkg = PptxPackage.open(deck)) {
            masterPartsInFile = pkg.entryNames().stream()
                    .filter(name -> name.matches("ppt/slideMasters/slideMaster\\d+\\.xml"))
                    .count();
        }

        long layoutPartsInFile;
        try (PptxPackage pkg = PptxPackage.open(deck)) {
            layoutPartsInFile = pkg.entryNames().stream()
                    .filter(name -> name.matches("ppt/slideLayouts/slideLayout\\d+\\.xml"))
                    .count();
        }

        try (var pres = new Presentation(deck.toString())) {
            assertThat(pres.getMasters().size())
                    .as("masters reported for a deck whose package contains %d of them",
                            masterPartsInFile)
                    .isEqualTo((int) masterPartsInFile);
            assertThat(pres.getMasters().get(0).getLayoutSlides().size())
                    .as("layouts on the master of a deck whose package contains %d of them",
                            layoutPartsInFile)
                    .isEqualTo((int) layoutPartsInFile);
        }
    }