@Test
    void testIndexOf() {
        try (var pres = new Presentation()) {
            ILayoutSlide layout = pres.getLayoutSlides().get(0);
            pres.getSlides().addEmptySlide(layout);
            assertThat(pres.getSlides().indexOf(pres.getSlides().get(0))).isEqualTo(0);
            assertThat(pres.getSlides().indexOf(pres.getSlides().get(1))).isEqualTo(1);
        }
    }