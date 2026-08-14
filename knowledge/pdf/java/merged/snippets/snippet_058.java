@Test
    void cellAdd_textbox_wrapsInFormFieldParagraph() throws Exception {
        try (Document doc = new Document()) {
            Page page = doc.getPages().add();
            Cell cell = new Cell();

            TextBoxField tf = new TextBoxField(page, new Rectangle(50, 700, 250, 720));
            cell.add(tf);

            BaseParagraph p = cell.getParagraphs().get(0);
            assertTrue(p instanceof FormFieldParagraph);
            assertSame(tf, ((FormFieldParagraph) p).asField());
        }
    }