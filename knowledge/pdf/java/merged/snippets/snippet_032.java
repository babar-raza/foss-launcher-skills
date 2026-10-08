@Test
    public void border_setAndRead_rgb() throws Exception {
        try (Document doc = new Document()) {
            Page page = doc.getPages().add();
            WidgetAnnotation w = new WidgetAnnotation(page, new Rectangle(0, 0, 100, 50));
            w.getCharacteristics().setBorder(Color.fromRgb(1, 0, 0));
            Color got = w.getCharacteristics().getBorder();
            assertNotNull(got);
            assertEquals(1.0, got.getR(), 0.01);
            assertEquals(0.0, got.getG(), 0.01);
            assertEquals(0.0, got.getB(), 0.01);
        }
    }