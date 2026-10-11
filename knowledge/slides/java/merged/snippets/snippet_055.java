@Test
    void aClonedSlideMustCarryTheShapesOfItsSource() throws Exception {
        Path out = tempDir.resolve("cloned.pptx");
        try (var pres = new Presentation()) {
            ISlide source = pres.getSlides().get(0);
            IAutoShape shape = source.getShapes()
                    .addAutoShape(ShapeType.RECTANGLE, 50, 50, 200, 100);
            shape.addTextFrame("Cloned content");
            pres.getSlides().addClone(source);
            pres.save(out.toString(), SaveFormat.PPTX);
        }

        try (PptxPackage pkg = PptxPackage.open(out)) {
            PackageAssertions.assertRegisteredSlideCount(pkg, 2);
        }
        assertThat(ThirdPartyReadBack.textOf(out, 1))
                .as("text an independent reader finds on the cloned slide of %s", out)
                .anySatisfy(text -> assertThat(text).contains("Cloned content"));
    }