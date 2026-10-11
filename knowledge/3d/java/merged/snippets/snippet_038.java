@Test
    public void evaluateAt_ShouldThrowUnsupportedOperationException() {
        NurbsCurve curve = new NurbsCurve();

        assertThrows(UnsupportedOperationException.class, () -> curve.evaluateAt(0.5));
    }