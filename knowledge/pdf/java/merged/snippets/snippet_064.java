@Test
    void setOpenAction_thenGet_roundTrips() throws IOException {
        PdfDictionary catalog = new PdfDictionary();
        DocumentActions actions = new DocumentActions(catalog, null);

        GoToURIAction goTo = new GoToURIAction("https://example.com");
        actions.setOpenAction(goTo);

        PdfAction read = actions.getOpenAction();
        assertNotNull(read);
        assertEquals("URI", read.getType());
        assertTrue(read instanceof UriAction);
        assertEquals("https://example.com", ((UriAction) read).getUri());

        // Catalog entry actually written
        assertNotNull(catalog.get(PdfName.of("OpenAction")));
    }