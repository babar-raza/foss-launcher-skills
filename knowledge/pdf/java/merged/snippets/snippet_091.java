@Test
    public void activationLifecycle() {
        assertFalse(RgbPrintShift.active());
        RgbPrintShift.setActive(true);
        assertFalse(RgbPrintShift.active(), "must stay off without acrobatPrintParity");

        System.setProperty("render.acrobatPrintParity", "true");
        RgbPrintShift.setActive(true);
        assertTrue(RgbPrintShift.active());
        RgbPrintShift.clear();
        assertFalse(RgbPrintShift.active());

        System.setProperty("render.printParityRgbShift", "false");
        RgbPrintShift.setActive(true);
        assertFalse(RgbPrintShift.active(), "kill switch must win");
    }