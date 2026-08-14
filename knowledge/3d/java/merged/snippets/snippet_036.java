@Test
    public void curveType_ShouldBeSettable() {
        NurbsCurve curve = new NurbsCurve();
        curve.setCurveType(NurbsType.CLOSED);

        assertEquals(NurbsType.CLOSED, curve.getCurveType());
    }