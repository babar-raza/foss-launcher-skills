@Test
    public void dwt53_constantLow_zeroHigh_reconstructsConstant() {
        int len = 16;
        int halfLen = (len + 1) / 2;
        int[] buf = new int[len];
        for (int i = 0; i < halfLen; i++) buf[i] = 1000;       // low (LL)
        // high (HL) already zero

        JPXDecodeFilter.inverseDWT53_1D(buf, 0, len);

        for (int i = 0; i < len; i++) {
            assertEquals(1000, buf[i], "5/3 IDWT of constant-low should reproduce constant; idx " + i);
        }
    }