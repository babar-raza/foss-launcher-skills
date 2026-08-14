@Test
    void testRemoveCustomProperty() {
        try (Presentation pres = new Presentation()) {
            IDocumentProperties props = pres.getDocumentProperties();
            props.setCustomPropertyValue("A", "val");
            props.setCustomPropertyValue("B", "val");
            assertThat(props.getCountOfCustomProperties()).isEqualTo(2);

            props.removeCustomProperty("A");
            assertThat(props.getCountOfCustomProperties()).isEqualTo(1);
            assertThat(props.containsCustomProperty("A")).isFalse();
            assertThat(props.containsCustomProperty("B")).isTrue();
        }
    }