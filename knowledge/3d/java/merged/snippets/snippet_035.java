@Test
    public void dimension_ShouldBeSettable() {
        NurbsCurve curve = new NurbsCurve();
        curve.setDimension(CurveDimension.TWO_DIMENSIONAL);

        assertEquals(CurveDimension.TWO_DIMENSIONAL, curve.getDimension());
    }