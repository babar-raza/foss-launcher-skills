@Test
    void anIndependentReaderMustSeeTheFormattingThatWasAskedFor() throws Exception {
        Path out = writeFormattedRun("run-readback.pptx");

        try (PptxPackage pkg = PptxPackage.open(out)) {
            Element run = PackageAssertions.selectNodes(
                    pkg, "ppt/slides/slide1.xml", "//p:txBody/a:p/a:r").get(0);
            List<Element> properties = PackageAssertions.selectNodes(
                    pkg, "ppt/slides/slide1.xml", "//p:txBody/a:p/a:r/a:rPr");
            assertThat(properties).as("a:rPr in %s", out).hasSize(1);
            assertThat(PackageAssertions.childNames(run).indexOf("a:rPr"))
                    .as("position of a:rPr among the children of a:r in %s", out)
                    .isZero();
        }
        assertThat(ThirdPartyReadBack.textOf(out, 0))
                .as("text an independent reader finds in %s", out)
                .anySatisfy(text -> assertThat(text).contains("Bold 24pt blue"));
    }