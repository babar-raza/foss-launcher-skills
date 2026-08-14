@Test
    void cellAdd_checkbox_wrapsInFormFieldParagraph() throws Exception {
        try (Document doc = new Document()) {
            Page page = doc.getPages().add();
            Cell cell = new Cell();

            CheckboxField cb = new CheckboxField(page, new Rectangle(50, 700, 70, 720));
            cell.add(cb);

            BaseParagraph p = cell.getParagraphs().get(0);
            assertTrue(p instanceof FormFieldParagraph);
            assertSame(cb, ((FormFieldParagraph) p).asField());
            assertNull(((FormFieldParagraph) p).asOption());
        }
    }