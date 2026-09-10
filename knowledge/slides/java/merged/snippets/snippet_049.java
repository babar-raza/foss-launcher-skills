@Test
    void savingAgainWithoutChangesMustNotChangeTheSlideXml() throws Exception {
        Path source = Fixtures.authoredDeck(tempDir, "source.pptx", "First");

        Path first = tempDir.resolve("first.pptx");
        try (var pres = new Presentation(source.toString())) {
            pres.save(first.toString(), SaveFormat.PPTX);
        }

        Path second = tempDir.resolve("second.pptx");
        try (var pres = new Presentation(first.toString())) {
            pres.save(second.toString(), SaveFormat.PPTX);
        }

        try (PptxPackage before = PptxPackage.open(first);
             PptxPackage after = PptxPackage.open(second)) {
            assertThat(after.text("ppt/slides/slide1.xml"))
                    .as("slide 1 of %s after a no-op re-save", second)
                    .isEqualTo(before.text("ppt/slides/slide1.xml"));
        }
    }