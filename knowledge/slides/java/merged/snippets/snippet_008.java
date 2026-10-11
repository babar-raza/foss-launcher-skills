@Test
    void theAdvertisedWordCountMustCountWordsSeparatedByAnyWhitespace() throws Exception {
        Path out = tempDir.resolve("words.pptx");
        try (var pres = new Presentation()) {
            IAutoShape shape = pres.getSlides().get(0).getShapes()
                    .addAutoShape(ShapeType.RECTANGLE, 50, 50, 400, 200);
            shape.addTextFrame("alpha\tbeta gamma");
            pres.save(out.toString(), SaveFormat.PPTX);
        }

        try (PptxPackage pkg = PptxPackage.open(out)) {
            List<Element> words = PackageAssertions.selectNodes(pkg, "docProps/app.xml",
                    "//ep:Words");
            assertThat(words)
                    .as("ep:Words element in docProps/app.xml of %s", out)
                    .hasSize(1);
            assertThat(words.get(0).getTextContent())
                    .as("word count advertised by docProps/app.xml of %s, whose one text run "
                            + "is 'alpha<tab>beta gamma'%n%s", out, pkg.text("docProps/app.xml"))
                    .isEqualTo("3");
        }
    }