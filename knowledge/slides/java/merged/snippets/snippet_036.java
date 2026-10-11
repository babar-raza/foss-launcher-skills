@Test
    void aParagraphAddedThroughTheCollectionMustReachTheFile() throws Exception {
        Path out = tempDir.resolve("paragraphs.pptx");
        try (var pres = new Presentation()) {
            IAutoShape shape = pres.getSlides().get(0).getShapes()
                    .addAutoShape(ShapeType.RECTANGLE, 50, 50, 400, 200);
            shape.addTextFrame("First paragraph");
            Paragraph second = new Paragraph();
            second.setText("Second paragraph");
            shape.getTextFrame().getParagraphs().add(second);
            pres.save(out.toString(), SaveFormat.PPTX);
        }

        try (PptxPackage pkg = PptxPackage.open(out)) {
            List<Element> paragraphs = PackageAssertions.selectNodes(
                    pkg, "ppt/slides/slide1.xml", "//p:txBody/a:p");
            assertThat(paragraphs)
                    .as("a:p elements in slide 1 of %s%n%s",
                            out, pkg.text("ppt/slides/slide1.xml"))
                    .hasSize(2);
        }
        assertThat(String.join("\n", ThirdPartyReadBack.textOf(out, 0)))
                .as("text an independent reader finds in %s", out)
                .contains("First paragraph")
                .contains("Second paragraph");
    }