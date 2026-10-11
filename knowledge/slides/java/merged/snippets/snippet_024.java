@Test
    void dangingRelationshipReferenceIsDetected() throws IOException {
        Path good = Fixtures.authoredDeck(tempDir, "good.pptx", "One");
        Path tampered = ZipSurgery.copyWithReplacement(good, tempDir.resolve("dangling.pptx"),
                "ppt/slides/slide1.xml",
                xml -> xml.replace("</p:spTree>",
                        "<p:pic xmlns:p=\"" + PptxPackage.NS_P + "\">"
                                + "<p:blipFill xmlns:a=\"" + PptxPackage.NS_A + "\">"
                                + "<a:blip xmlns:r=\"" + PptxPackage.NS_REL
                                + "\" r:embed=\"rIdNoSuchThing\"/>"
                                + "</p:blipFill></p:pic></p:spTree>"));
        try (PptxPackage pkg = PptxPackage.open(tampered)) {
            assertThat(catchAssertionError(
                    () -> PackageAssertions.assertEveryRelationshipReferenceResolves(pkg)))
                    .as("the rule must reject an r:embed with no matching Relationship")
                    .isNotNull()
                    .hasMessageContaining("rIdNoSuchThing");
        }
    }