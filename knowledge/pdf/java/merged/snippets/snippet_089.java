@Test
    public void saturatedCyanCrushesRed() {
        int out = RgbPrintShift.shift(0xFF000000 | (45 << 16) | (109 << 8) | 146);
        assertEquals(0, (out >> 16) & 0xFF);
        assertTrue(Math.abs(((out >> 8) & 0xFF) - 109) <= 1);
        assertTrue(Math.abs((out & 0xFF) - 148) <= 2);
    }