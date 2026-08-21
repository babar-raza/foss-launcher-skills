@Test
    void inverseRoundTripsThroughTheLattice() {
        double[][] probes = {
                {0, 0, 0, 0.6}, {0.977, 0.745, 0.025, 0}, {0.5, 0, 0, 0},
                {0.742, 0.676, 0.668, 0.895}, {0, 0, 0, 0}};
        for (double[] p : probes) {
            int rgb = CmykPrintLut.toRGBInt(p[0], p[1], p[2], p[3]);
            double[] ink = CmykPrintLut.inverse(rgb);
            double[] back = CmykPrintLut.toRGB(ink[0], ink[1], ink[2], ink[3]);
            for (int ch = 0; ch < 3; ch++) {
                double want = (rgb >> (16 - 8 * ch)) & 0xFF;
                assertTrue(Math.abs(back[ch] - want) <= 4,
                        "channel " + ch + " off by " + Math.abs(back[ch] - want)
                                + " for cmyk " + java.util.Arrays.toString(p));
            }
        }
    }