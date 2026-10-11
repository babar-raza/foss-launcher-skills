@Test
    public void caption_setAndRead() throws Exception {
        try (Document doc = new Document()) {
            Page page = doc.getPages().add();
            WidgetAnnotation w = new WidgetAnnotation(page, new Rectangle(0, 0, 100, 50));
            assertNull(w.getCharacteristics().getCaption());
            w.getCharacteristics().setCaption("Submit");
            assertEquals("Submit", w.getCharacteristics().getCaption());
            w.getCharacteristics().setCaption(null);
            assertNull(w.getCharacteristics().getCaption());
        }
    }