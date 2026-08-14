@Test
    void testAddAutoShape() {
        try (var pres = new Presentation()) {
            var slide = blankSlide(pres);
            var shape = slide.getShapes().addAutoShape(ShapeType.RECTANGLE, 50, 50, 200, 100);
            assertThat(slide.getShapes().size()).isEqualTo(1);
            assertThat(shape.getShapeType()).isEqualTo(ShapeType.RECTANGLE);
        }
    }