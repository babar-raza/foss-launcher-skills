@Test
    void setOpenAction_null_removesEntry() {
        PdfDictionary catalog = new PdfDictionary();
        DocumentActions actions = new DocumentActions(catalog, null);

        actions.setOpenAction(new GoToURIAction("https://x"));
        assertNotNull(catalog.get(PdfName.of("OpenAction")));

        actions.setOpenAction(null);
        assertNull(catalog.get(PdfName.of("OpenAction")));
    }