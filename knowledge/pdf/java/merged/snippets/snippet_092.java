@Test
    public void dwt97_constantLow_K_check_alternate() {
        int len = 16;
        int halfLen = (len + 1) / 2;
        double[] buf = new double[len];
        for (int i = 0; i < halfLen; i++) buf[i] = K_97;       // low = K

        JPXDecodeFilter.inverseDWT97_1D(buf, 0, len);

        System.out.println("[dwt97] feed K=" + K_97 + " expect ?");
        for (int i = 0; i < len; i++) {
            System.out.printf("  out[%d] = %.6f%n", i, buf[i]);
        }
    }