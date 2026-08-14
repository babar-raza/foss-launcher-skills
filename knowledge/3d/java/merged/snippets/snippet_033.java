@Test
    public void degree_ShouldBeSettable() {
        NurbsCurve curve = new NurbsCurve();
        curve.setDegree(2);

        assertEquals(3, curve.getOrder());
        assertEquals(2, curve.getDegree());
    }