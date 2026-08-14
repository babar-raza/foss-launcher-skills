@Test
    void testSlideName() throws IOException {
        try (var pres = new Presentation()) {
            pres.getSlides().get(0).setName("MySlide");
            assertThat(pres.getSlides().get(0).getName()).isEqualTo("MySlide");

            try (var pres2 = saveAndReopen(pres)) {
                assertThat(pres2.getSlides().get(0).getName()).isEqualTo("MySlide");
            }
        }
    }