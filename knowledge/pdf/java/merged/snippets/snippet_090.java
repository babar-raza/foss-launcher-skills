@Test
    public void dwt97_constantLow_zeroHigh_reconstructsConstant() {
        int len = 16;
        int halfLen = (len + 1) / 2;
        double[] buf = new double[len];
        // If forward 9/7 of constant-1 input produces LL = 1/K (low samples
        // divided by K), then inverse should be fed 1/K to recover 1.
        // We feed K^-1 directly and expect 1.0 output.
        for (int i = 0; i < halfLen; i++) buf[i] = 1.0 / K_97; // low

        JPXDecodeFilter.inverseDWT97_1D(buf, 0, len);

        for (int i = 0; i < len; i++) {
            assertEquals(1.0, buf[i], EPS_97,
                    "9/7 IDWT of (1/K, ..., 1/K | 0,...,0) should reconstruct 1; idx " + i);
        }
    }