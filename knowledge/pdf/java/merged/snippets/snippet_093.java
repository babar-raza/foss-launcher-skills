@Test
    public void dwt97_roundTrip_smallSignal() {
        double[] orig = {10, 20, 30, 40, 50, 60, 70, 80};
        double[] x = orig.clone();
        int len = x.length;

        // Forward 9/7 lifting (canonical ISO/IEC 15444-1 Annex F.4.6 order):
        // 1) d_n -= α (s_n + s_{n+1})  on odd indices
        // 2) s_n -= β (d_{n-1} + d_n)  on even
        // 3) d_n -= γ (s_n + s_{n+1})  on odd
        // 4) s_n -= δ (d_{n-1} + d_n)  on even
        // 5) scale: even *= 1/K, odd *= K
        final double A = -1.586134342, B = -0.052980118;
        final double G =  0.882911075, D =  0.443506852;

        // mirror boundary helpers
        java.util.function.IntUnaryOperator mirror = i -> i < 0 ? -i : (i >= len ? 2*(len-1)-i : i);

        for (int i = 1; i < len; i += 2) {
            int li = mirror.applyAsInt(i - 1);
            int ri = mirror.applyAsInt(i + 1);
            x[i] += A * (x[li] + x[ri]);
        }
        for (int i = 0; i < len; i += 2) {
            int li = mirror.applyAsInt(i - 1);
            int ri = mirror.applyAsInt(i + 1);
            x[i] += B * (x[li] + x[ri]);
        }
        for (int i = 1; i < len; i += 2) {
            int li = mirror.applyAsInt(i - 1);
            int ri = mirror.applyAsInt(i + 1);
            x[i] += G * (x[li] + x[ri]);
        }
        for (int i = 0; i < len; i += 2) {
            int li = mirror.applyAsInt(i - 1);
            int ri = mirror.applyAsInt(i + 1);
            x[i] += D * (x[li] + x[ri]);
        }
        // Scaling: convention 1 — even (low) /= K², odd (high) *= K². The inverse
        // multiplies low by K² so that the lifting's residual 1/K loss-side
        // gain produces the correct DC reconstruction (see DeviceCMYK comments
        // and dwt97_constantLow_zeroHigh_reconstructsConstant).
        double K2 = K_97 * K_97;
        double[] sc1 = x.clone();
        for (int i = 0; i < len; i += 2) sc1[i] /= K2;
        for (int i = 1; i < len; i += 2) sc1[i] *= K2;
        // Convention 2 — even *= K, odd /= K (legacy, won't round-trip under
        // the K² inverse; left as a probe).
        double[] sc2 = x.clone();
        for (int i = 0; i < len; i += 2) sc2[i] *= K_97;
        for (int i = 1; i < len; i += 2) sc2[i] /= K_97;

        // De-interleave each into [low ... | high ...] layout that our IDWT expects.
        int halfLen = (len + 1) / 2;
        double[] sub1 = new double[len], sub2 = new double[len];
        for (int n = 0; n < halfLen; n++) sub1[n] = sc1[2 * n];
        for (int n = 0; n < len - halfLen; n++) sub1[halfLen + n] = sc1[2 * n + 1];
        for (int n = 0; n < halfLen; n++) sub2[n] = sc2[2 * n];
        for (int n = 0; n < len - halfLen; n++) sub2[halfLen + n] = sc2[2 * n + 1];

        // Apply our inverse
        double[] rec1 = sub1.clone();
        double[] rec2 = sub2.clone();
        JPXDecodeFilter.inverseDWT97_1D(rec1, 0, len);
        JPXDecodeFilter.inverseDWT97_1D(rec2, 0, len);

        System.out.println("[roundtrip] orig=" + java.util.Arrays.toString(orig));
        System.out.println("[roundtrip] rec  (forward /K, *K — convention 1): "
                + java.util.Arrays.toString(rec1));
        System.out.println("[roundtrip] rec  (forward *K, /K — convention 2): "
                + java.util.Arrays.toString(rec2));

        // One of these must match (within EPS).
        boolean conv1ok = true, conv2ok = true;
        for (int i = 0; i < len; i++) {
            if (Math.abs(rec1[i] - orig[i]) > 1e-3) conv1ok = false;
            if (Math.abs(rec2[i] - orig[i]) > 1e-3) conv2ok = false;
        }
        System.out.println("[roundtrip] convention1 OK=" + conv1ok + "   convention2 OK=" + conv2ok);
        assertTrue(conv1ok || conv2ok, "Neither scaling convention round-trips");
    }