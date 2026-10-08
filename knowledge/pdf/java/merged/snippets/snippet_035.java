@Test
    public void rotate_default_isZero() throws Exception {
        try (Document doc = new Document()) {
            Page page = doc.getPages().add();
            WidgetAnnotation w = new WidgetAnnotation(page, new Rectangle(0, 0, 100, 50));
            assertEquals(0, w.getCharacteristics().getRotate());
        }
    }