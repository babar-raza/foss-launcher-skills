@Test
    void testSaveAndReload() throws IOException {
        try (var pres = new Presentation()) {
            try (var pres2 = saveAndReopen(pres)) {
                assertThat(pres2.getSlides().size()).isEqualTo(1);
            }
        }
    }