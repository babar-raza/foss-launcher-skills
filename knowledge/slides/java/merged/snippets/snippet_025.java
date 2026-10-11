@Test
    void partWithoutAContentTypeIsDetected() throws IOException {
        Path good = Fixtures.authoredDeck(tempDir, "good.pptx", "One");
        Path tampered = ZipSurgery.copyWithExtraPart(good, tempDir.resolve("untyped.pptx"),
                "ppt/media/image1.unknownext", new byte[]{1, 2, 3});
        try (PptxPackage pkg = PptxPackage.open(tampered)) {
            assertThat(catchAssertionError(
                    () -> PackageAssertions.assertEveryPartHasAContentType(pkg)))
                    .as("the rule must reject a part with no Override and no Default")
                    .isNotNull()
                    .hasMessageContaining("image1.unknownext");
        }
    }