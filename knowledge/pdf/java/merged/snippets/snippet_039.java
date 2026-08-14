@Test
    void getText_defaultsToNull() throws Exception {
        try (Document doc = new Document()) {
            Page p = doc.getPages().add();
            WatermarkAnnotation w = new WatermarkAnnotation(p, new Rectangle(0, 0, 100, 100));
            assertNull(w.getText());
        }
    }