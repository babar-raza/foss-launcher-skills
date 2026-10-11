@Test
    void slideCountIgnoresSlidePartsThatAreNotRegistered() throws IOException {
        Path good = Fixtures.authoredDeck(tempDir, "good.pptx", "One");
        Path tampered = ZipSurgery.copyWithExtraPart(good, tempDir.resolve("orphan.pptx"),
                "ppt/slides/slide99.xml", "<?xml version=\"1.0\"?><root/>".getBytes());
        try (PptxPackage pkg = PptxPackage.open(tampered)) {
            assertThat(PackageAssertions.registeredSlideCount(pkg))
                    .as("an unregistered slide part must not be counted as a slide")
                    .isEqualTo(1);
        }
    }