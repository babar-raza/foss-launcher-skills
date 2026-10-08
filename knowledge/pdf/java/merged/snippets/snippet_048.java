@Test
    void newFreeText_hasNoneByDefault() throws Exception {
        try (Document doc = new Document()) {
            Page p = doc.getPages().add();
            FreeTextAnnotation ft = new FreeTextAnnotation(p, new Rectangle(0, 0, 100, 50));
            assertEquals(LineEnding.None, ft.getEndingStyle());
        }
    }