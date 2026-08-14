@Test
    public void multiplicity_ShouldBeWritable() {
        NurbsCurve curve = new NurbsCurve();
        java.util.List<Integer> multiplicity = curve.getMultiplicity();

        assertNotNull(multiplicity);
        assertEquals(0, multiplicity.size());

        multiplicity.add(2);
        assertEquals(1, multiplicity.size());
    }