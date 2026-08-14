@Test
    void testFirstSlideNumber() throws IOException {
        try (var pres = new Presentation()) {
            pres.setFirstSlideNumber(5);
            assertThat(pres.getFirstSlideNumber()).isEqualTo(5);

            try (var pres2 = saveAndReopen(pres)) {
                assertThat(pres2.getFirstSlideNumber()).isEqualTo(5);
            }
        }
    }