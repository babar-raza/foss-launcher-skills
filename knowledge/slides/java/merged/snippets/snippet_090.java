@Test
    void testRemoveSlideAt() {
        try (var pres = new Presentation()) {
            ILayoutSlide layout = pres.getLayoutSlides().get(0);
            pres.getSlides().addEmptySlide(layout);
            pres.getSlides().removeAt(1);
            assertThat(pres.getSlides().size()).isEqualTo(1);
        }
    }