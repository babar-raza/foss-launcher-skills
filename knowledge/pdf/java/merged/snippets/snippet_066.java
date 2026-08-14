@Test
    void setAfterPrinting_thenGet_roundTrips() throws IOException {
        PdfDictionary catalog = new PdfDictionary();
        DocumentActions actions = new DocumentActions(catalog, null);

        actions.setAfterPrinting(new GoToURIAction("https://done"));
        PdfAction read = actions.getAfterPrinting();
        assertNotNull(read);
        assertTrue(read instanceof UriAction);

        // /AA dictionary was created with the /DP entry
        PdfDictionary aa = (PdfDictionary) catalog.get(PdfName.of("AA"));
        assertNotNull(aa);
        assertNotNull(aa.get(PdfName.of("DP")));
    }