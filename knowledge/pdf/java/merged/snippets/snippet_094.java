@Test
    public void emptyDictionary() throws IOException {
        PdfDictionary dict = new PdfDictionary();
        assertTrue(dict.isEmpty());
        assertEquals(0, dict.size());
        String result = writeTo(dict);
        assertTrue(result.contains("<<"));
        assertTrue(result.contains(">>"));
    }