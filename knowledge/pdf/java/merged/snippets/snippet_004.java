@Test
    public void border_clear_removesEntry() throws Exception {
        try (Document doc = new Document()) {
            Page page = doc.getPages().add();
            WidgetAnnotation w = new WidgetAnnotation(page, new Rectangle(0, 0, 100, 50));
            w.getCharacteristics().setBorder(Color.fromRgb(0, 1, 0));
            assertNotNull(w.getCharacteristics().getBorder());
            w.getCharacteristics().setBorder(null);
            assertNull(w.getCharacteristics().getBorder());
        }
    }