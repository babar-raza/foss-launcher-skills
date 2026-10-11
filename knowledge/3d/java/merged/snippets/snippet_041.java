@Test
    public void multiplicity_ShouldBeWritable() {
        NurbsDirection direction = new NurbsDirection();
        java.util.List<Integer> multiplicity = direction.getMultiplicity();

        assertNotNull(multiplicity);
        assertEquals(0, multiplicity.size());

        multiplicity.add(2);
        assertEquals(1, multiplicity.size());
    }