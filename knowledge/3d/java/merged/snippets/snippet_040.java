@Test
    public void knotVectors_ShouldBeWritable() {
        NurbsDirection direction = new NurbsDirection();
        java.util.List<Double> knotVectors = direction.getKnotVectors();

        assertNotNull(knotVectors);
        assertEquals(0, knotVectors.size());

        knotVectors.add(0.0);
        knotVectors.add(1.0);
        assertEquals(2, knotVectors.size());
    }