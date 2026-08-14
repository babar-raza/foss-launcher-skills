@Test
    public void callout_twoPoints_setAndRead() throws Exception {
        try (Document doc = new Document()) {
            Page page = doc.getPages().add();
            DefaultAppearance da = new DefaultAppearance();
            FreeTextAnnotation fta = new FreeTextAnnotation(page,
                    new Rectangle(0, 0, 100, 50), da);
            fta.setCallout(new double[][] {{0, 0}, {200, 100}});
            double[][] cl = fta.getCallout();
            assertNotNull(cl);
            assertEquals(2, cl.length);
            assertEquals(200.0, cl[1][0], 0.001);
        }
    }