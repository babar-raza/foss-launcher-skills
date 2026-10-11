@Test
    public void rational_ShouldBeSettable() {
        NurbsCurve curve = new NurbsCurve();
        curve.setRational(true);

        assertTrue(curve.getRational());
    }