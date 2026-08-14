@Test
    public void squigglyAnnotation_rectCtor_derivesQuadPoints() throws Exception {
        try (Document doc = new Document()) {
            Page page = doc.getPages().add();
            SquigglyAnnotation sq = new SquigglyAnnotation(page, new Rectangle(50, 100, 200, 120));
            double[] qp = sq.getQuadPoints();
            assertNotNull(qp);
            assertEquals(8, qp.length);
        }
    }