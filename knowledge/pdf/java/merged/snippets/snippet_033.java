@Test
    public void underlineAnnotation_rectCtor_derivesQuadPoints() throws Exception {
        try (Document doc = new Document()) {
            Page page = doc.getPages().add();
            UnderlineAnnotation u = new UnderlineAnnotation(page, new Rectangle(50, 100, 200, 120));
            double[] qp = u.getQuadPoints();
            assertNotNull(qp);
            assertEquals(8, qp.length);
        }
    }