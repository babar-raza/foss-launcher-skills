@Test
    void childOrderViolationIsDetected() throws IOException {
        Path good = Fixtures.authoredDeck(tempDir, "good.pptx", "One");
        try (PptxPackage pkg = PptxPackage.open(good)) {
            var spTree = PackageAssertions.selectNodes(pkg, "ppt/slides/slide1.xml",
                    "//p:cSld/p:spTree").get(0);
            assertThat(catchAssertionError(() -> PackageAssertions.assertChildrenInSchemaOrder(
                    spTree, "p:sp", "p:nvGrpSpPr", "p:grpSpPr")))
                    .as("the rule must reject children that appear out of sequence")
                    .isNotNull()
                    .hasMessageContaining("is not the schema order");
        }
    }