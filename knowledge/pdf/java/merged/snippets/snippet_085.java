@Test
    void cellAdd_radioOption_wrapsInFormFieldParagraph() throws Exception {
        try (Document doc = new Document()) {
            Page page = doc.getPages().add();
            Cell cell = new Cell();

            RadioButtonOptionField opt = new RadioButtonOptionField(page,
                    new Rectangle(50, 700, 70, 720));
            opt.setOptionName("Red");
            cell.add(opt);

            assertEquals(1, cell.getParagraphs().size());
            BaseParagraph p = cell.getParagraphs().get(0);
            assertTrue(p instanceof FormFieldParagraph,
                    "Expected FormFieldParagraph wrapper, got " + p.getClass().getSimpleName());
            FormFieldParagraph ffp = (FormFieldParagraph) p;
            assertSame(opt, ffp.getField());
            assertSame(opt, ffp.asOption());
            assertNull(ffp.asField(), "RBOF is not a Field subclass");
        }
    }