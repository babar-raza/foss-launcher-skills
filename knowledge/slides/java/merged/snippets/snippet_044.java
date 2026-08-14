@Test
    void testAddImage() throws IOException {
        try (Presentation pres = new Presentation()) {
            pres.getImages().addImage(createTestPng(255, 0, 0));
            assertThat(pres.getImages().size()).isGreaterThanOrEqualTo(1);
        }
    }