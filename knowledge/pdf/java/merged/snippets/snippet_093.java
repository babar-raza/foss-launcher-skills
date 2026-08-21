@Test
    public void workingSpaceMultiplyMatchesGold() {
        // Y = (1, 0.963, 0.5) -> (255, 245.6, 127.5)
        int y = 0xFFFFF680; // 255,246,128 (8-bit quantized paint value)
        int yu = RgbPrintShift.unshift(RgbPrintShift.shift(y));
        int r = ((yu >> 16) & 0xFF) * ((yu >> 16) & 0xFF) / 255;
        int g = ((yu >> 8) & 0xFF) * ((yu >> 8) & 0xFF) / 255;
        int b = (yu & 0xFF) * (yu & 0xFF) / 255;
        int out = RgbPrintShift.shift(0xFF000000 | (r << 16) | (g << 8) | b);
        assertTrue(Math.abs(((out >> 16) & 0xFF) - 255) <= 1, "R " + ((out >> 16) & 0xFF));
        assertTrue(Math.abs(((out >> 8) & 0xFF) - 238) <= 2, "G " + ((out >> 8) & 0xFF));
        assertTrue(Math.abs((out & 0xFF) - 30) <= 3, "B " + (out & 0xFF));
    }