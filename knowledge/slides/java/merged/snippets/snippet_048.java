@Test
    void savingAgainWithoutChangesMustNotChangeTheFileSize() throws Exception {
        Path source = Fixtures.authoredDeck(tempDir, "source.pptx", "First", "Second");

        Path first = tempDir.resolve("first.pptx");
        try (var pres = new Presentation(source.toString())) {
            pres.save(first.toString(), SaveFormat.PPTX);
        }

        Path second = tempDir.resolve("second.pptx");
        try (var pres = new Presentation(first.toString())) {
            pres.save(second.toString(), SaveFormat.PPTX);
        }

        assertThat(Files.size(second))
                .as("size after re-saving %s unchanged (first save was %d bytes)",
                        first, Files.size(first))
                .isEqualTo(Files.size(first));
    }