@Test
    public void order_ShouldBeSettable() {
        NurbsCurve curve = new NurbsCurve();
        curve.setOrder(4);

        assertEquals(4, curve.getOrder());
        assertEquals(3, curve.getDegree());
    }