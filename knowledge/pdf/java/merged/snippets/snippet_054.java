@Test
    public void rotate_defaultIsZero() throws Exception {
        try (Document doc = new Document()) {
            Page page = doc.getPages().add();
            DefaultAppearance da = new DefaultAppearance();
            FreeTextAnnotation fta = new FreeTextAnnotation(page,
                    new Rectangle(0, 0, 100, 50), da);
            assertEquals(0, fta.getRotate());
        }
    }