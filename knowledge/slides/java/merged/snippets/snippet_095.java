@Test
    void testCustomIntProperty() throws IOException {
        try (var pres = new Presentation()) {
            pres.getDocumentProperties().setCustomPropertyValue("Count", 42);

            try (var pres2 = saveAndReopen(pres)) {
                List<Object> out = new ArrayList<>();
                out.add(null);
                pres2.getDocumentProperties().getCustomPropertyValue("Count", out);
                assertThat(out.get(0)).isEqualTo(42);
            }
        }
    }