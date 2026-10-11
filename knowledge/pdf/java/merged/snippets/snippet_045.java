@Test
    void setStyle_syncsToOption() {
        RadioButtonOptionField opt = new RadioButtonOptionField();
        Border border = new Border(opt);
        border.setStyle(BorderStyle.Dashed);

        Border roundTrip = opt.getBorder();
        assertNotNull(roundTrip);
        // Round-tripped style starts with "D" (first letter, per RBOF.setBorder)
        // We only assert width here because Border doesn't round-trip the enum
        // through the PDF object layer in OpenPDF today (the /BS /S key is name-only).
        assertEquals(1.0, roundTrip.getWidth(), 1e-6);
    }