@Test
    public void rotate_setAndRead() throws Exception {
        try (Document doc = new Document()) {
            Page page = doc.getPages().add();
            WidgetAnnotation w = new WidgetAnnotation(page, new Rectangle(0, 0, 100, 50));
            w.getCharacteristics().setRotate(90);
            assertEquals(90, w.getCharacteristics().getRotate());
            w.getCharacteristics().setRotate(270);
            assertEquals(270, w.getCharacteristics().getRotate());
        }
    }