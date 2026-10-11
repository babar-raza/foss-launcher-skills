@Test
    public void callout_setNull_removes() throws Exception {
        try (Document doc = new Document()) {
            Page page = doc.getPages().add();
            DefaultAppearance da = new DefaultAppearance();
            FreeTextAnnotation fta = new FreeTextAnnotation(page,
                    new Rectangle(0, 0, 100, 50), da);
            fta.setCallout(new double[][] {{0, 0}, {1, 1}});
            assertNotNull(fta.getCallout());
            fta.setCallout(null);
            assertNull(fta.getCallout());
        }
    }