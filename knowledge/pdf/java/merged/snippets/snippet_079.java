private static void assertFinder(boolean[][] m, int row, int col) {
        // 7x7: solid dark border ring, light inner ring, 3x3 dark centre.
        for (int dy = 0; dy < 7; dy++) {
            for (int dx = 0; dx < 7; dx++) {
                int ring = Math.min(Math.min(dx, dy), Math.min(6 - dx, 6 - dy));
                boolean expectDark = ring != 1; // ring 1 is the light separator inside the border
                assertEquals(expectDark, m[row + dy][col + dx],
                        "finder@(" + row + "," + col + ") module (" + dy + "," + dx + ")");
            }
        }
    }