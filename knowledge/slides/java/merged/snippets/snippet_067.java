@Test
    void testContextManager() {
        try (Presentation pres = new Presentation()) {
            assertThat(pres.getSlides().size()).isGreaterThanOrEqualTo(1);
        }
    }