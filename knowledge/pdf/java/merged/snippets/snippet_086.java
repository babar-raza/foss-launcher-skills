private static void assertShift(int r, int g, int b, int er, int eg, int eb, int tol) {
        int out = RgbPrintShift.shift(0xFF000000 | (r << 16) | (g << 8) | b);
        int or = (out >> 16) & 0xFF, og = (out >> 8) & 0xFF, ob = out & 0xFF;
        assertTrue(Math.abs(or - er) <= tol && Math.abs(og - eg) <= tol
                        && Math.abs(ob - eb) <= tol,
                String.format("(%d,%d,%d) -> (%d,%d,%d), expected (%d,%d,%d)",
                        r, g, b, or, og, ob, er, eg, eb));
    }