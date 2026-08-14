@Test
    void codewordStreamMatchesSpecExample() {
        QrEncoder.Encoded e = QrEncoder.buildCodewords("01234567".getBytes(), "01234567",
                QrEncoder.Ecc.MEDIUM);
        assertEquals(1, e.version, "numeric 8-digit payload fits version 1");
        int[] expected = new int[SPEC_DATA.length + SPEC_ECC.length];
        System.arraycopy(SPEC_DATA, 0, expected, 0, SPEC_DATA.length);
        System.arraycopy(SPEC_ECC, 0, expected, SPEC_DATA.length, SPEC_ECC.length);
        assertArrayEquals(toBytes(expected), e.codewords,
                "v1-M single block: data codewords followed by ECC codewords");
    }