@Test
    void aRemovedSlideMustBeGoneFromTheSavedFile() throws Exception {
        Path source = Fixtures.authoredDeck(tempDir, "three.pptx", "First", "Second", "Third");
        Path out = tempDir.resolve("removed.pptx");
        try (var pres = new Presentation(source.toString())) {
            pres.getSlides().removeAt(1);
            pres.save(out.toString(), SaveFormat.PPTX);
        }

        try (PptxPackage pkg = PptxPackage.open(out)) {
            PackageAssertions.assertRegisteredSlideCount(pkg, 2);
            PackageAssertions.assertPackageIsSelfConsistent(pkg);
        }
        assertThat(ThirdPartyReadBack.slideCount(out))
                .as("slides an independent reader finds after removing one from %s", out)
                .isEqualTo(2);
    }