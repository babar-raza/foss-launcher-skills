@Test
    void allFiveAAEntries_setIndependently() throws IOException {
        PdfDictionary catalog = new PdfDictionary();
        DocumentActions actions = new DocumentActions(catalog, null);

        actions.setBeforeClosing(new GoToURIAction("https://a"));
        actions.setBeforeSaving(new GoToURIAction("https://b"));
        actions.setAfterSaving(new GoToURIAction("https://c"));
        actions.setBeforePrinting(new GoToURIAction("https://d"));
        actions.setAfterPrinting(new GoToURIAction("https://e"));

        assertEquals("https://a", ((UriAction) actions.getBeforeClosing()).getUri());
        assertEquals("https://b", ((UriAction) actions.getBeforeSaving()).getUri());
        assertEquals("https://c", ((UriAction) actions.getAfterSaving()).getUri());
        assertEquals("https://d", ((UriAction) actions.getBeforePrinting()).getUri());
        assertEquals("https://e", ((UriAction) actions.getAfterPrinting()).getUri());
    }