@Test
    void aSlideRemovedByReferenceMustBeGoneFromTheSavedFile() throws Exception {
        Path source = Fixtures.authoredDeck(tempDir, "three.pptx", "First", "Second", "Third");
        Path out = tempDir.resolve("removed-by-ref.pptx");
        try (var pres = new Presentation(source.toString())) {
            pres.getSlides().remove(pres.getSlides().get(2));
            pres.save(out.toString(), SaveFormat.PPTX);
        }

        try (PptxPackage pkg = PptxPackage.open(out)) {
            PackageAssertions.assertRegisteredSlideCount(pkg, 2);
        }
    }