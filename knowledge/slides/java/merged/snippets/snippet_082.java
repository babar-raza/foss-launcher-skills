@Test
    void testReorderShapes() {
        try (var pres = new Presentation()) {
            var slide = blankSlide(pres);
            slide.getShapes().addAutoShape(ShapeType.RECTANGLE, 50, 50, 200, 100);
            var ellipse = slide.getShapes().addAutoShape(ShapeType.ELLIPSE, 300, 50, 150, 150);
            slide.getShapes().reorder(0, ellipse);
            assertThat(slide.getShapes().get(0).getShapeType()).isEqualTo(ShapeType.ELLIPSE);
        }
    }