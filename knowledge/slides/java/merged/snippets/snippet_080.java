@Test
    void testClearShapes() {
        try (var pres = new Presentation()) {
            var slide = pres.getSlides().get(0);
            slide.getShapes().addAutoShape(ShapeType.RECTANGLE, 50, 50, 200, 100);
            slide.getShapes().clear();
            assertThat(slide.getShapes().size()).isEqualTo(0);
        }
    }