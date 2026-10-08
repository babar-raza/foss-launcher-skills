@Test
    public void allFourSubtypesAreSet() throws Exception {
        try (Document doc = new Document()) {
            Page page = doc.getPages().add();
            Rectangle r = new Rectangle(10, 20, 30, 40);
            assertEquals("Highlight",
                    new HighlightAnnotation(page, r).getSubtype());
            assertEquals("Underline",
                    new UnderlineAnnotation(page, r).getSubtype());
            assertEquals("StrikeOut",
                    new StrikeOutAnnotation(page, r).getSubtype());
            assertEquals("Squiggly",
                    new SquigglyAnnotation(page, r).getSubtype());
        }
    }