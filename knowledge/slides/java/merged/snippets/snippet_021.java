@Test
    void testCoreProperties() throws IOException {
        try (var pres = new Presentation()) {
            IDocumentProperties props = pres.getDocumentProperties();
            props.setTitle("My Presentation");
            props.setSubject("Demo Subject");
            props.setAuthor("John Doe");
            props.setKeywords("demo, test");
            props.setCategory("Examples");

            try (var pres2 = saveAndReopen(pres)) {
                IDocumentProperties p2 = pres2.getDocumentProperties();
                assertThat(p2.getTitle()).isEqualTo("My Presentation");
                assertThat(p2.getSubject()).isEqualTo("Demo Subject");
                assertThat(p2.getAuthor()).isEqualTo("John Doe");
                assertThat(p2.getKeywords()).isEqualTo("demo, test");
                assertThat(p2.getCategory()).isEqualTo("Examples");
            }
        }
    }