@ParameterizedTest(name = "{0}")
    @EnumSource(SaveFormat.class)
    void savingInAFormatMustProduceThatFormatOrRefuse(SaveFormat format) throws Exception {
        String expectedContentType = MAIN_PART_CONTENT_TYPES.get(format);
        Path out = tempDir.resolve("deck." + format.name().toLowerCase(Locale.ROOT));

        try (var pres = new Presentation()) {
            if (expectedContentType == null) {
                Throwable thrown = catchThrowable(() -> pres.save(out.toString(), format));
                assertThat(thrown)
                        .as("saving as %s is not implemented and must say so, not write a "
                                + "PowerPoint package under a .%s name", format,
                                format.name().toLowerCase(Locale.ROOT))
                        .isInstanceOf(UnsupportedOperationException.class);
                assertThat(Files.exists(out))
                        .as("a refused save must not leave a file behind at %s", out)
                        .isFalse();
            } else {
                pres.save(out.toString(), format);
                try (PptxPackage pkg = PptxPackage.open(out)) {
                    assertThat(PackageAssertions.mainPartContentType(pkg))
                            .as("content type of /ppt/presentation.xml in %s", out)
                            .isEqualTo(expectedContentType);
                }
            }
        }
    }