@Test
    void aPortionAddedToAParagraphMustReachTheFileAsItsOwnRun() throws Exception {
        Path out = tempDir.resolve("portions.pptx");
        try (var pres = new Presentation()) {
            IAutoShape shape = pres.getSlides().get(0).getShapes()
                    .addAutoShape(ShapeType.RECTANGLE, 50, 50, 400, 200);
            shape.addTextFrame("Plain ");
            shape.getTextFrame().getParagraphs().get(0).getPortions()
                    .add(new Portion("and emphasised"));
            pres.save(out.toString(), SaveFormat.PPTX);
        }

        try (PptxPackage pkg = PptxPackage.open(out)) {
            List<Element> runs = PackageAssertions.selectNodes(
                    pkg, "ppt/slides/slide1.xml", "//p:txBody/a:p[1]/a:r");
            assertThat(runs)
                    .as("a:r elements in the first paragraph of %s%n%s",
                            out, pkg.text("ppt/slides/slide1.xml"))
                    .hasSize(2);
        }
    }