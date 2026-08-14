@Test
    void testRemoveSlideByRef() {
        try (var pres = new Presentation()) {
            ILayoutSlide layout = pres.getLayoutSlides().get(0);
            pres.getSlides().addEmptySlide(layout);
            assertThat(pres.getSlides().size()).isEqualTo(2);
            pres.getSlides().remove(pres.getSlides().get(1));
            assertThat(pres.getSlides().size()).isEqualTo(1);
        }
    }