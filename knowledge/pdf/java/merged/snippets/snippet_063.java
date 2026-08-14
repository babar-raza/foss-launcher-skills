@Test
    void emptyCatalog_allGettersReturnNull() {
        PdfDictionary catalog = new PdfDictionary();
        DocumentActions actions = new DocumentActions(catalog, null);

        assertNull(actions.getOpenAction());
        assertNull(actions.getBeforeClosing());
        assertNull(actions.getBeforeSaving());
        assertNull(actions.getAfterSaving());
        assertNull(actions.getBeforePrinting());
        assertNull(actions.getAfterPrinting());
    }