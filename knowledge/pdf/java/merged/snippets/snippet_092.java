@Test
    public void unshiftRoundTrip() {
        int[] samples = {0xFFC110A0, 0xFFFFB81C, 0xFF808080, 0xFF204060, 0xFFFFF67F};
        for (int argb : samples) {
            int rt = RgbPrintShift.shift(RgbPrintShift.unshift(argb));
            for (int sh = 0; sh <= 16; sh += 8) {
                assertTrue(Math.abs(((rt >> sh) & 0xFF) - ((argb >> sh) & 0xFF)) <= 1,
                        String.format("%08X -> %08X", argb, rt));
            }
        }
    }