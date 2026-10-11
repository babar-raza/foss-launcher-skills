@Test
    void savingASubsetToAStreamMustWriteOnlyTheRequestedSlides() throws Exception {
        Path source = Fixtures.authoredDeck(tempDir, "three.pptx", "First", "Second", "Third");
        Path out = tempDir.resolve("subset-stream.pptx");
        try (var pres = new Presentation(source.toString())) {
            var buffer = new ByteArrayOutputStream();
            pres.save(buffer, new int[]{0, 2}, SaveFormat.PPTX);
            java.nio.file.Files.write(out, buffer.toByteArray());
        }

        try (PptxPackage pkg = PptxPackage.open(out)) {
            PackageAssertions.assertRegisteredSlideCount(pkg, 2);
            // Kept in document order, whatever order they were named in.
            assertThat(slideTexts(pkg))
                    .as("the slides kept in %s, which was asked for slides 0 and 2 of "
                            + "[First, Second, Third]", out)
                    .containsExactly("First", "Third");
        }
    }