@Test
    void aTableMustLockGroupingWithTheElementTheStandardDefines() throws Exception {
        Path out = writeDeckWithTable();

        try (PptxPackage pkg = PptxPackage.open(out)) {
            List<Element> properties = PackageAssertions.selectNodes(
                    pkg, "ppt/slides/slide1.xml",
                    "//p:graphicFrame/p:nvGraphicFramePr/p:cNvGraphicFramePr");
            assertThat(properties)
                    .as("p:cNvGraphicFramePr elements in slide 1 of %s", out)
                    .hasSize(1);
            PackageAssertions.assertChildrenInSchemaOrder(
                    properties.get(0), "a:graphicFrameLocks", "a:extLst");
        }
    }