@Test
    void theSceneMustPrecedeTheShapeThreeDPropertiesWhicheverOrderTheyWereSetIn()
            throws Exception {
        Path out = tempDir.resolve("threed-order.pptx");
        try (var pres = new Presentation()) {
            IAutoShape shape = pres.getSlides().get(0).getShapes()
                    .addAutoShape(ShapeType.RECTANGLE, 50, 50, 200, 100);
            // Extrusion first: it creates <a:sp3d>, which <a:scene3d> must then be placed before.
            shape.getThreeDFormat().setExtrusionHeight(20);
            shape.getThreeDFormat().getCamera().setCameraType(CameraPresetType.PERSPECTIVE_FRONT);
            pres.save(out.toString(), SaveFormat.PPTX);
        }

        try (PptxPackage pkg = PptxPackage.open(out)) {
            Element shapeProperties = PackageAssertions.selectNodes(
                    pkg, "ppt/slides/slide1.xml", "//p:sp/p:spPr").get(0);
            List<String> children = PackageAssertions.childNames(shapeProperties);
            assertThat(children).as("children of p:spPr in %s", out)
                    .contains("a:scene3d", "a:sp3d");
            assertThat(children.indexOf("a:scene3d"))
                    .as("a:scene3d must come before a:sp3d; p:spPr children are %s in %s",
                            children, out)
                    .isLessThan(children.indexOf("a:sp3d"));
        }
    }