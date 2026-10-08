@Test
    public void strikeOutAnnotation_rectCtor_derivesQuadPoints() throws Exception {
        try (Document doc = new Document()) {
            Page page = doc.getPages().add();
            StrikeOutAnnotation s = new StrikeOutAnnotation(page, new Rectangle(50, 100, 200, 120));
            double[] qp = s.getQuadPoints();
            assertNotNull(qp);
            assertEquals(8, qp.length);
        }
    }