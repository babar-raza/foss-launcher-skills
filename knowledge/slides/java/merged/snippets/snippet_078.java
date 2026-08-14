@Test
    void testRemoveShape() {
        try (var pres = new Presentation()) {
            var slide = blankSlide(pres);
            var s = slide.getShapes().addAutoShape(ShapeType.RECTANGLE, 50, 50, 200, 100);
            slide.getShapes().addAutoShape(ShapeType.ELLIPSE, 300, 50, 150, 150);
            assertThat(slide.getShapes().size()).isEqualTo(2);
            slide.getShapes().remove(s);
            assertThat(slide.getShapes().size()).isEqualTo(1);
        }
    }