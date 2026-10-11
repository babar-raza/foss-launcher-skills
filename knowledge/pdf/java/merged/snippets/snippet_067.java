@Test
    void setText_andGet_roundTrip() throws Exception {
        try (Document doc = new Document()) {
            Page p = doc.getPages().add();
            WatermarkAnnotation w = new WatermarkAnnotation(p, new Rectangle(0, 0, 100, 100));
            w.setText("DRAFT");
            assertEquals("DRAFT", w.getText());
            assertEquals("DRAFT", w.getContents(), "setText delegates to /Contents");
        }
    }