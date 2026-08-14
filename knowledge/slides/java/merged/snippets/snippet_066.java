@Test
    void testSaveToStream() throws IOException {
        try (var pres = new Presentation()) {
            ByteArrayOutputStream buf = new ByteArrayOutputStream();
            pres.save(buf, SaveFormat.PPTX);
            assertThat(buf.size()).isGreaterThan(0);
        }
    }