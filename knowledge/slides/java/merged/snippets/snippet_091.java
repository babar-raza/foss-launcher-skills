@Test
    void testSlideHidden() throws IOException {
        try (var pres = new Presentation()) {
            pres.getSlides().get(0).setHidden(true);
            assertThat(pres.getSlides().get(0).isHidden()).isTrue();

            try (var pres2 = saveAndReopen(pres)) {
                assertThat(pres2.getSlides().get(0).isHidden()).isTrue();
            }
        }
    }