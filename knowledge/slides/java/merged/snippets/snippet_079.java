@Test
    void testRemoveAt() {
        try (var pres = new Presentation()) {
            var slide = blankSlide(pres);
            slide.getShapes().addAutoShape(ShapeType.RECTANGLE, 50, 50, 200, 100);
            slide.getShapes().addAutoShape(ShapeType.ELLIPSE, 300, 50, 150, 150);
            slide.getShapes().removeAt(0);
            assertThat(slide.getShapes().size()).isEqualTo(1);
        }
    }