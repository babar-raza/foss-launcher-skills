@Test
    public void rotate_setAndRead() throws Exception {
        try (Document doc = new Document()) {
            Page page = doc.getPages().add();
            DefaultAppearance da = new DefaultAppearance();
            FreeTextAnnotation fta = new FreeTextAnnotation(page,
                    new Rectangle(0, 0, 100, 50), da);
            fta.setRotate(180);
            assertEquals(180, fta.getRotate());
            fta.setRotate(90);
            assertEquals(90, fta.getRotate());
        }
    }