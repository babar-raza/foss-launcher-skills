@Test
    public void cosCtor_doesNotOverrideExistingQuadPoints() throws Exception {
        // Reload path: when constructed from an existing dictionary, QuadPoints
        // already on the dict must NOT be clobbered.
        try (Document doc = new Document()) {
            Page page = doc.getPages().add();
            HighlightAnnotation orig = new HighlightAnnotation(page, new Rectangle(0, 0, 100, 50));
            double[] custom = {1, 2, 3, 4, 5, 6, 7, 8};
            orig.setQuadPoints(custom);
            HighlightAnnotation reloaded = new HighlightAnnotation(orig.getPdfDictionary(), page);
            assertArrayEquals(custom, reloaded.getQuadPoints(), 0.001);
        }
    }