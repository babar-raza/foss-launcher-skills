@Test
    void theFormatsThatAreWrittenMustDifferFromEachOther() throws Exception {
        Set<String> contentTypes = new LinkedHashSet<>();
        for (SaveFormat format : MAIN_PART_CONTENT_TYPES.keySet()) {
            Path out = tempDir.resolve("distinct." + format.name().toLowerCase(Locale.ROOT));
            try (var pres = new Presentation()) {
                pres.save(out.toString(), format);
            }
            try (PptxPackage pkg = PptxPackage.open(out)) {
                contentTypes.add(PackageAssertions.mainPartContentType(pkg));
            }
        }
        assertThat(contentTypes)
                .as("each written format must declare its own main-part content type")
                .hasSize(MAIN_PART_CONTENT_TYPES.size());
    }