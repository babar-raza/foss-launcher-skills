@Test
    public void evaluate_ShouldThrowUnsupportedOperationException() {
        NurbsCurve curve = new NurbsCurve();

        assertThrows(UnsupportedOperationException.class, () -> curve.evaluate(10));
    }