@Test
    void testCustomStringProperty() throws IOException {
        try (var pres = new Presentation()) {
            pres.getDocumentProperties().setCustomPropertyValue("MyProp", "hello");

            try (var pres2 = saveAndReopen(pres)) {
                List<Object> out = new ArrayList<>();
                out.add(null);
                pres2.getDocumentProperties().getCustomPropertyValue("MyProp", out);
                assertThat(out.get(0)).isEqualTo("hello");
            }
        }
    }