@Test
    void savingASubsetMustWriteOnlyTheRequestedSlides() throws Exception {
        Path source = Fixtures.authoredDeck(tempDir, "three.pptx", "First", "Second", "Third");
        Path out = tempDir.resolve("subset.pptx");
        try (var pres = new Presentation(source.toString())) {
            pres.save(out.toString(), new int[]{1}, SaveFormat.PPTX);
        }

        try (PptxPackage pkg = PptxPackage.open(out)) {
            PackageAssertions.assertRegisteredSlideCount(pkg, 1);
            PackageAssertions.assertPackageIsSelfConsistent(pkg);
            // The count alone would be satisfied by keeping the wrong slide.
            assertThat(slideTexts(pkg))
                    .as("the slides kept in %s, which was asked for slide 1 of "
                            + "[First, Second, Third]", out)
                    .containsExactly("Second");
        }
    }