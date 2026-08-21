@Test
    public void neutralsFollowMeasuredToneCurve() {
        assertShift(255, 255, 255, 255, 255, 255, 0);
        assertShift(0, 0, 0, 0, 0, 0, 0);
        assertShift(32, 32, 32, 26, 26, 26, 1);
        assertShift(64, 64, 64, 62, 62, 62, 1);
        assertShift(96, 96, 96, 95, 95, 95, 1);
        assertShift(128, 128, 128, 129, 129, 129, 1);
    }