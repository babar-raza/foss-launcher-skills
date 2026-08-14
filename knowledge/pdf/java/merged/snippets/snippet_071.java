@Test
    void reedSolomonMatchesSpecExample() {
        byte[] data = toBytes(SPEC_DATA);
        byte[] ecc = QrEncoder.rsRemainder(data, QrEncoder.rsGenerator(10));
        assertArrayEquals(toBytes(SPEC_ECC), ecc, "RS ECC codewords must match ISO 18004 Annex I");
    }