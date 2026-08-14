@Test
    public void dwt97_zeroLow_zeroHigh_isZero() {
        double[] buf = new double[16];
        JPXDecodeFilter.inverseDWT97_1D(buf, 0, 16);
        for (int i = 0; i < 16; i++) {
            assertEquals(0.0, buf[i], EPS_97, "zero in → zero out, idx " + i);
        }
    }