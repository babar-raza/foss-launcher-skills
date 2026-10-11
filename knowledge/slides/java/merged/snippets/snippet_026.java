@Test
    void overrideNamingAMissingPartIsDetected() throws IOException {
        Path good = Fixtures.authoredDeck(tempDir, "good.pptx", "One", "Two");
        Path tampered = ZipSurgery.copyWithoutPart(good, tempDir.resolve("halfdeleted.pptx"),
                "ppt/slides/slide2.xml");
        try (PptxPackage pkg = PptxPackage.open(tampered)) {
            assertThat(catchAssertionError(
                    () -> PackageAssertions.assertNoContentTypeOverrideNamesAMissingPart(pkg)))
                    .as("the rule must reject an Override for a part that was removed")
                    .isNotNull()
                    .hasMessageContaining("/ppt/slides/slide2.xml");
        }
    }