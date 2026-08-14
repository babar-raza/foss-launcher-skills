@Test
    void capacityTableMatchesSpec() {
        assertEquals(19, QrEncoder.numDataCodewords(1, QrEncoder.Ecc.LOW));
        assertEquals(16, QrEncoder.numDataCodewords(1, QrEncoder.Ecc.MEDIUM));
        assertEquals(13, QrEncoder.numDataCodewords(1, QrEncoder.Ecc.QUARTILE));
        assertEquals(9, QrEncoder.numDataCodewords(1, QrEncoder.Ecc.HIGH));
        assertEquals(2956, QrEncoder.numDataCodewords(40, QrEncoder.Ecc.LOW));
        assertEquals(3706, QrEncoder.numRawDataModules(40) / 8);
    }