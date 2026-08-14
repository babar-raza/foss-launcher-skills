@Test
    public void callout_invalidLength_isNoOp() throws Exception {
        try (Document doc = new Document()) {
            Page page = doc.getPages().add();
            DefaultAppearance da = new DefaultAppearance();
            FreeTextAnnotation fta = new FreeTextAnnotation(page,
                    new Rectangle(0, 0, 100, 50), da);
            fta.setCallout(new double[][] {{0, 0}, {1, 1}});
            // 4 points is not allowed — the set should be a no-op
            fta.setCallout(new double[][] {{0, 0}, {1, 1}, {2, 2}, {3, 3}});
            double[][] cl = fta.getCallout();
            assertNotNull(cl);
            assertEquals(2, cl.length, "Original 2-point callout should be preserved on invalid set");
        }
    }