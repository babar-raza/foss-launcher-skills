@Test
    void writtenFixtureIsANonEmptyZip() throws IOException {
        Path good = Fixtures.authoredDeck(tempDir, "good.pptx", "One");
        assertThat(Files.size(good)).isGreaterThan(0);
        try (PptxPackage pkg = PptxPackage.open(good)) {
            assertThat(pkg.entryNames()).contains("[Content_Types].xml", "ppt/presentation.xml");
        }
    }