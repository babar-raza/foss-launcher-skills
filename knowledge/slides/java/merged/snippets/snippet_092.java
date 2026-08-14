@Test
    void testCloneSlide() {
        try (var pres = new Presentation()) {
            ISlide slide = pres.getSlides().get(0);
            slide.getShapes().addAutoShape(ShapeType.RECTANGLE, 50, 50, 200, 100);
            pres.getSlides().addClone(slide);
            assertThat(pres.getSlides().size()).isEqualTo(2);
            assertThat(pres.getSlides().get(1).getShapes().size()).isGreaterThanOrEqualTo(1);
        }
    }