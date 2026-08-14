@Test
    public void getCharacteristics_neverNull() throws Exception {
        try (Document doc = new Document()) {
            Page page = doc.getPages().add();
            WidgetAnnotation w = new WidgetAnnotation(page, new Rectangle(0, 0, 100, 50));
            assertNotNull(w.getCharacteristics());
        }
    }