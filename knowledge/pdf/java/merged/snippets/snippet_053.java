@Test
    public void intent_setAndRead() throws Exception {
        try (Document doc = new Document()) {
            Page page = doc.getPages().add();
            DefaultAppearance da = new DefaultAppearance("Helv", 10, Color.BLACK);
            FreeTextAnnotation fta = new FreeTextAnnotation(page,
                    new Rectangle(50, 50, 200, 100), da);

            fta.setIntent(FreeTextIntent.FreeTextCallout);
            assertEquals(FreeTextIntent.FreeTextCallout, fta.getIntent());

            fta.setIntent(FreeTextIntent.FreeTextTypeWriter);
            assertEquals(FreeTextIntent.FreeTextTypeWriter, fta.getIntent());

            // Setting Undefined removes the entry
            fta.setIntent(FreeTextIntent.Undefined);
            assertEquals(FreeTextIntent.Undefined, fta.getIntent());

            // Setting null removes the entry
            fta.setIntent(FreeTextIntent.FreeText);
            assertEquals(FreeTextIntent.FreeText, fta.getIntent());
            fta.setIntent(null);
            assertEquals(FreeTextIntent.Undefined, fta.getIntent());
        }
    }