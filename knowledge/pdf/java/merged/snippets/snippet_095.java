@Test
    public void testMissingFont() throws IOException {
        FontRepository repo = new FontRepository();
        PdfDictionary fontsDict = new PdfDictionary();
        PdfFont font = repo.getFont(fontsDict, "F1", null);
        assertNull(font);
    }