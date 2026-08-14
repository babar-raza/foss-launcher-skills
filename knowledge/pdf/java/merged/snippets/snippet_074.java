@Test
    void finderPatternsAtThreeCorners() {
        boolean[][] m = QrEncoder.encode("HELLO WORLD", QrEncoder.Ecc.QUARTILE);
        int n = m.length;
        assertFinder(m, 0, 0);
        assertFinder(m, 0, n - 7);
        assertFinder(m, n - 7, 0);
        // The fourth corner carries NO finder (only data / an alignment pattern nearby).
        assertFalse(isFinderRow(m, n - 7, n - 7), "no finder in the bottom-right corner");
    }