@Test
    public void constructor_ShouldInitializeDefaultValues() {
        NurbsCurve curve = new NurbsCurve();

        assertNotNull(curve);
        assertEquals(2, curve.getOrder());
        assertEquals(1, curve.getDegree());
        assertFalse(curve.getRational());
        assertEquals(CurveDimension.THREE_DIMENSIONAL, curve.getDimension());
        assertEquals(NurbsType.OPEN, curve.getCurveType());
    }