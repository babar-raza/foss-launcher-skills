@Test
    void runChildrenMustFollowTheSchemaSequence() throws Exception {
        Path out = writeFormattedRun("run-sequence.pptx");

        try (PptxPackage pkg = PptxPackage.open(out)) {
            Element run = PackageAssertions.selectNodes(
                    pkg, "ppt/slides/slide1.xml", "//p:txBody/a:p/a:r").get(0);
            PackageAssertions.assertChildrenInSchemaOrder(run, "a:rPr", "a:t");
        }
    }