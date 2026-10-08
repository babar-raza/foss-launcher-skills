@Test
    public void headingsAndParagraphs() throws IOException {
        SdmDocument doc = new SdmDocument();
        Heading h1 = new Heading(1);
        h1.getInline().add(new Run("Title", null));
        Heading h3 = new Heading(3);
        h3.getInline().add(new Run("Section", null));
        doc.getChildren().add(h1);
        doc.getChildren().add(para("Body text one."));
        doc.getChildren().add(h3);
        doc.getChildren().add(para("Body text two."));

        Element body = bodyOf(new SdmHtmlWriter().write(doc));
        List<Element> top = kids(body);
        assertEquals(4, top.size());
        assertEquals("h1", top.get(0).getNodeName().toLowerCase());
        assertEquals("Title", textOf(top.get(0)));
        assertEquals("p", top.get(1).getNodeName().toLowerCase());
        assertEquals("Body text one.", textOf(top.get(1)));
        assertEquals("h3", top.get(2).getNodeName().toLowerCase());
        assertEquals("Section", textOf(top.get(2)));
        assertEquals("p", top.get(3).getNodeName().toLowerCase());
    }