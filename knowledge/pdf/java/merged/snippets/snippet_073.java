@Test
    void symbolSizeIsVersionDependent() {
        assertEquals(21, QrEncoder.encode("01234567", QrEncoder.Ecc.MEDIUM).length); // v1 = 21x21
        // A long byte payload forces a higher version (larger grid), still square.
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < 300; i++) {
            sb.append('A');
        }
        boolean[][] big = QrEncoder.encodeBytes(sb.toString().getBytes(), QrEncoder.Ecc.LOW);
        assertTrue(big.length > 21 && big.length == big[0].length, "higher version, square grid");
        assertEquals(0, (big.length - 17) % 4, "size = 4*version + 17");
    }