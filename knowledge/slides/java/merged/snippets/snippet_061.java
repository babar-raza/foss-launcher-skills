@Test
    void characterFormattingMustBeWrittenBeforeTheTextItApplies() throws Exception {
        Path out = writeFormattedRun("run-order.pptx");

        try (PptxPackage pkg = PptxPackage.open(out)) {
            List<Element> runs = PackageAssertions.selectNodes(
                    pkg, "ppt/slides/slide1.xml", "//p:txBody/a:p/a:r");
            assertThat(runs).as("runs in slide 1 of %s", out).hasSize(1);
            assertThat(PackageAssertions.childNames(runs.get(0)))
                    .as("children of <a:r> in %s", out)
                    .containsExactly("a:rPr", "a:t");
        }
    }