@Test
    void testLoadExisting() throws IOException {
        Path path = Path.of("src", "test", "resources", "aspose", "slidesfoss",
                "test_data", "Presentation.pptx");
        assumeThat(Files.exists(path))
                .as("Presentation.pptx not found in test_data")
                .isTrue();
        try (var pres = new Presentation(path.toString())) {
            assertThat(pres.getSlides().size()).isGreaterThanOrEqualTo(1);
        }
    }