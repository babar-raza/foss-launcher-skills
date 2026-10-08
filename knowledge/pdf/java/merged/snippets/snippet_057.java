@Test
    public void callout_threePoints_setAndRead() throws Exception {
        try (Document doc = new Document()) {
            Page page = doc.getPages().add();
            DefaultAppearance da = new DefaultAppearance();
            FreeTextAnnotation fta = new FreeTextAnnotation(page,
                    new Rectangle(0, 0, 100, 50), da);
            fta.setCallout(new double[][] {{10, 10}, {50, 50}, {100, 100}});
            double[][] cl = fta.getCallout();
            assertNotNull(cl);
            assertEquals(3, cl.length);
            assertEquals(10.0, cl[0][0], 0.001);
            assertEquals(10.0, cl[0][1], 0.001);
            assertEquals(50.0, cl[1][0], 0.001);
            assertEquals(100.0, cl[2][0], 0.001);
            assertEquals(100.0, cl[2][1], 0.001);
        }
    }