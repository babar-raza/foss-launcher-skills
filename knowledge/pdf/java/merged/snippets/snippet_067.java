@Test
    void setAfterPrinting_null_removesEntry_andPrunesAAIfEmpty() {
        PdfDictionary catalog = new PdfDictionary();
        DocumentActions actions = new DocumentActions(catalog, null);

        actions.setAfterPrinting(new GoToURIAction("https://x"));
        actions.setBeforeSaving(new GoToURIAction("https://y"));

        // Clear only DP: AA should still exist with WS
        actions.setAfterPrinting(null);
        PdfDictionary aa = (PdfDictionary) catalog.get(PdfName.of("AA"));
        assertNotNull(aa, "/AA should remain while WS is still set");
        assertNotNull(aa.get(PdfName.of("WS")));

        // Clear the last one: /AA itself should go away
        actions.setBeforeSaving(null);
        assertNull(catalog.get(PdfName.of("AA")), "/AA should be pruned when empty");
    }