@Test
    void testSlideLayoutAccess() {
        try (var pres = new Presentation()) {
            assertThat(pres.getSlides().get(0).getLayoutSlide()).isNotNull();
        }
    }