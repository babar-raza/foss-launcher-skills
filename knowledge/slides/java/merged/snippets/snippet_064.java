@Test
    void testCreateEmpty() {
        try (var pres = new Presentation()) {
            assertThat(pres.getSlides().size()).isEqualTo(1);
        }
    }