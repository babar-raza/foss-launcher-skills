@Test
    public void background_setAndRead() throws Exception {
        try (Document doc = new Document()) {
            Page page = doc.getPages().add();
            WidgetAnnotation w = new WidgetAnnotation(page, new Rectangle(0, 0, 100, 50));
            w.getCharacteristics().setBackground(Color.fromRgb(0, 0.5, 0.5));
            Color got = w.getCharacteristics().getBackground();
            assertNotNull(got);
            assertEquals(0.5, got.getG(), 0.01);
        }
    }