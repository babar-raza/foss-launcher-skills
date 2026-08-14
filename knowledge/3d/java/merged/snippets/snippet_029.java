@Test
    public void controlPoints_ShouldBeWritable() {
        NurbsCurve curve = new NurbsCurve();
        java.util.List<Vector4> controlPoints = curve.getControlPoints();

        assertNotNull(controlPoints);
        assertEquals(0, controlPoints.size());

        controlPoints.add(new Vector4(1, 2, 3, 1));
        assertEquals(1, controlPoints.size());
    }