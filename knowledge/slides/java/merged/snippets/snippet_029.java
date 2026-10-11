@Test
    void childrenInSchemaOrderAreAccepted() throws IOException {
        Path good = Fixtures.authoredDeck(tempDir, "good.pptx", "One");
        try (PptxPackage pkg = PptxPackage.open(good)) {
            var spTree = PackageAssertions.selectNodes(pkg, "ppt/slides/slide1.xml",
                    "//p:cSld/p:spTree").get(0);
            assertThat(catchAssertionError(() -> PackageAssertions.assertChildrenInSchemaOrder(
                    spTree, "p:nvGrpSpPr", "p:grpSpPr", "p:sp")))
                    .as("the rule must accept children that are in sequence")
                    .isNull();
        }
    }