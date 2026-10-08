@Test
    public void intent_defaultIsUndefined() throws Exception {
        try (Document doc = new Document()) {
            Page page = doc.getPages().add();
            DefaultAppearance da = new DefaultAppearance("Helv", 10, Color.BLACK);
            FreeTextAnnotation fta = new FreeTextAnnotation(page,
                    new Rectangle(50, 50, 200, 100), da);
            assertEquals(FreeTextIntent.Undefined, fta.getIntent());
        }
    }