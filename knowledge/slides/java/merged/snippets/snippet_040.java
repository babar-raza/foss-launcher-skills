@Test
    void replacingTheTextMustNotLeaveABlankParagraphBehind() throws Exception {
        Path out = tempDir.resolve("replaced.pptx");
        try (var pres = new Presentation()) {
            IAutoShape shape = pres.getSlides().get(0).getShapes()
                    .addAutoShape(ShapeType.RECTANGLE, 50, 50, 400, 200);
            shape.addTextFrame("First text");
            shape.getTextFrame().setText("Replacement line one\nReplacement line two");
            pres.save(out.toString(), SaveFormat.PPTX);
        }

        try (PptxPackage pkg = PptxPackage.open(out)) {
            assertThat(PackageAssertions.selectNodes(pkg, "ppt/slides/slide1.xml",
                    "//p:sp/p:txBody/a:p"))
                    .as("a:p elements in the shape's text body of %s%n%s",
                            out, pkg.text("ppt/slides/slide1.xml"))
                    .hasSize(2);
        }
    }