@Test
    void setOpacity_andGet_roundTrip() throws Exception {
        try (Document doc = new Document()) {
            Page p = doc.getPages().add();
            WatermarkAnnotation w = new WatermarkAnnotation(p, new Rectangle(0, 0, 100, 100));
            assertEquals(1.0, w.getOpacity(), 1e-6, "default = 1.0");
            w.setOpacity(0.4);
            assertEquals(0.4, w.getOpacity(), 1e-6);
        }
    }