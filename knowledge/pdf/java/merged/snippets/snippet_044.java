@Test
    void setWidth_syncsToOption() {
        RadioButtonOptionField opt = new RadioButtonOptionField();
        Border border = new Border(opt);
        border.setWidth(2.5);

        // Border is stored on the option through setBorder
        Border roundTrip = opt.getBorder();
        assertNotNull(roundTrip, "option should now have a Border via syncParent");
        assertEquals(2.5, roundTrip.getWidth(), 1e-6);
    }