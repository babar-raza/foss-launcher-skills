@Test
    public void highlightAnnotation_rectCtor_derivesQuadPoints() throws Exception {
        try (Document doc = new Document()) {
            Page page = doc.getPages().add();
            Rectangle rect = new Rectangle(100, 200, 300, 250);
            HighlightAnnotation h = new HighlightAnnotation(page, rect);
            double[] qp = h.getQuadPoints();
            assertNotNull(qp, "QuadPoints should be auto-derived");
            assertEquals(8, qp.length);
            // top-left
            assertEquals(100.0, qp[0], 0.001);
            assertEquals(250.0, qp[1], 0.001);
            // top-right
            assertEquals(300.0, qp[2], 0.001);
            assertEquals(250.0, qp[3], 0.001);
            // bottom-left
            assertEquals(100.0, qp[4], 0.001);
            assertEquals(200.0, qp[5], 0.001);
            // bottom-right
            assertEquals(300.0, qp[6], 0.001);
            assertEquals(200.0, qp[7], 0.001);
        }
    }