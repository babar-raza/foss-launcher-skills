@Test
    void setAngle_andGet_roundTrip() throws Exception {
        try (Document doc = new Document()) {
            Page p = doc.getPages().add();
            WatermarkAnnotation w = new WatermarkAnnotation(p, new Rectangle(0, 0, 100, 100));
            assertEquals(0, w.getAngle(), 1e-6, "default = 0");
            w.setAngle(45);
            assertEquals(45, w.getAngle(), 1e-6);
        }
    }