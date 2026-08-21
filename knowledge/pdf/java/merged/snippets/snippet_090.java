@Test
    public void alphaPreserved() {
        int out = RgbPrintShift.shift(0x7F000000 | (10 << 16) | (200 << 8) | 30);
        assertEquals(0x7F, out >>> 24);
    }