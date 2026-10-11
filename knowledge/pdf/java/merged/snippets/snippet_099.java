@Test
    public void elementAlternativeText() {
        PdfDictionary catalog = new PdfDictionary();
        TaggedContent tc = new TaggedContent(null, catalog, null);
        FigureElement fig = tc.createFigureElement();
        fig.setAlternativeText("Graph");
        assertEquals("Graph", fig.getAlternativeText());
        assertEquals("Graph", fig.getAlternateDescription());
    }