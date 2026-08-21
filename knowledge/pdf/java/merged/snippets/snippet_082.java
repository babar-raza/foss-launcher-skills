@Test
    void latticeCornersMatchMeasurement() {
        // white paper and solid magenta, measured from the printed chart
        assertEquals(0xFFFFFFFF, CmykPrintLut.toRGBInt(0, 0, 0, 0));
        int magenta = CmykPrintLut.toRGBInt(0, 1, 0, 0);
        assertEquals(246, (magenta >> 16) & 0xFF);
        assertEquals(86, (magenta >> 8) & 0xFF);
        assertEquals(160, magenta & 0xFF);
    }