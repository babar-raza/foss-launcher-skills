@Test
    void timingPatternsAlternate() {
        boolean[][] m = QrEncoder.encode("01234567", QrEncoder.Ecc.LOW);
        // Row 6 and column 6 between the finders alternate dark/light, starting dark at index 8.
        for (int i = 8; i <= m.length - 9; i++) {
            assertEquals(i % 2 == 0, m[6][i], "horizontal timing module " + i);
            assertEquals(i % 2 == 0, m[i][6], "vertical timing module " + i);
        }
    }