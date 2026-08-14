@ParameterizedTest(name = "dash style {0} can be set on shape line format")
    @MethodSource("dashStyles")
    void testMultipleDashStyles(LineDashStyle style) {
        try (var pres = new Presentation()) {
            var slide = pres.getSlides().get(0);
            var shape = slide.getShapes().addAutoShape(ShapeType.RECTANGLE, 50, 50, 200, 50);
            shape.getLineFormat().setDashStyle(style);
            assertThat(shape.getLineFormat().getDashStyle()).isEqualTo(style);
        }
    }