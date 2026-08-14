@Test
    void document_getActions_returnsLiveView() throws IOException {
        try (Document doc = new Document()) {
            doc.getPages().add();
            DocumentActions actions = doc.getActions();
            assertNotNull(actions);
            assertNull(actions.getOpenAction());

            actions.setOpenAction(new GoToURIAction("https://example.com"));
            // Re-fetch a new view; same catalog → entry visible
            assertNotNull(doc.getActions().getOpenAction());
        }
    }