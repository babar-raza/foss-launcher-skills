@Test
    void testIterateSlides() {
        try (var pres = new Presentation()) {
            ILayoutSlide layout = pres.getLayoutSlides().get(0);
            pres.getSlides().addEmptySlide(layout);
            List<ISlide> slides = new ArrayList<>();
            for (ISlide slide : pres.getSlides()) {
                slides.add(slide);
            }
            assertThat(slides).hasSize(2);
        }
    }