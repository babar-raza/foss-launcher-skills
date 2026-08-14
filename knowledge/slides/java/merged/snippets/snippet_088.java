@Test
    void testInsertEmptySlide() {
        try (var pres = new Presentation()) {
            ILayoutSlide layout = pres.getLayoutSlides().get(0);
            pres.getSlides().addEmptySlide(layout);
            pres.getSlides().insertEmptySlide(1, layout);
            assertThat(pres.getSlides().size()).isEqualTo(3);
        }
    }