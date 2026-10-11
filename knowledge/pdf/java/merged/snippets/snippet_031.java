@Test
    public void getCharacteristics_isCached() throws Exception {
        try (Document doc = new Document()) {
            Page page = doc.getPages().add();
            WidgetAnnotation w = new WidgetAnnotation(page, new Rectangle(0, 0, 100, 50));
            AppearanceCharacteristics first = w.getCharacteristics();
            AppearanceCharacteristics second = w.getCharacteristics();
            assertSame(first, second, "getCharacteristics() should return the same instance");
        }
    }