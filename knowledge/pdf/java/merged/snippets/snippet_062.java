@Test
    void formFieldParagraph_ctorNull_throws() {
        assertThrows(IllegalArgumentException.class,
                () -> new FormFieldParagraph((org.aspose.pdf.forms.Field) null));
        assertThrows(IllegalArgumentException.class,
                () -> new FormFieldParagraph((RadioButtonOptionField) null));
    }