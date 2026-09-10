@Test
    void theAdvertisedSlideCountMustMatchTheSlidesInTheFile() throws Exception {
        Path source = Fixtures.authoredDeck(tempDir, "three.pptx", "First", "Second", "Third");
        Path out = tempDir.resolve("resaved.pptx");
        try (var pres = new Presentation(source.toString())) {
            pres.save(out.toString(), SaveFormat.PPTX);
        }

        try (PptxPackage pkg = PptxPackage.open(out)) {
            int slides = PackageAssertions.registeredSlideCount(pkg);
            assertThat(slides)
                    .as("the fixture must have several slides for this test to mean anything")
                    .isEqualTo(3);

            List<Element> declared = PackageAssertions.selectNodes(
                    pkg, "docProps/app.xml", "//ep:Slides");
            assertThat(declared).as("ep:Slides element in docProps/app.xml of %s", out)
                    .hasSize(1);
            assertThat(declared.get(0).getTextContent())
                    .as("slide count advertised by docProps/app.xml of %s, which has %d slides",
                            out, slides)
                    .isEqualTo(String.valueOf(slides));
        }
    }