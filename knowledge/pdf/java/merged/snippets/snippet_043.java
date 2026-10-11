@Test
    void ctor_storesReferenceAndPropsDefault() {
        RadioButtonOptionField opt = new RadioButtonOptionField();
        Border border = new Border(opt);
        assertNotNull(border);
        assertEquals(1.0, border.getWidth(), 1e-6, "default width = 1");
        assertEquals(BorderStyle.Solid, border.getStyle(), "default style = Solid");
    }