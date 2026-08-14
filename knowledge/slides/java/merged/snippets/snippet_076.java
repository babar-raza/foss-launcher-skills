@Test
    void testMultipleShapeTypes() {
        ShapeType[] types = {ShapeType.RECTANGLE, ShapeType.ELLIPSE, ShapeType.TRIANGLE};
        try (var pres = new Presentation()) {
            var slide = blankSlide(pres);
            for (ShapeType st : types) {
                var s = slide.getShapes().addAutoShape(st, 10, 10, 100, 100);
                assertThat(s.getShapeType()).isEqualTo(st);
            }
            assertThat(slide.getShapes().size()).isEqualTo(3);
        }
    }