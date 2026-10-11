@Test
    public void constructor_ShouldInitializeDefaultValues() {
        NurbsDirection direction = new NurbsDirection();

        assertNotNull(direction);
        assertEquals(3, direction.getOrder());
        assertEquals(2, direction.getDegree());
        assertEquals(10, direction.getDivisions());
        assertEquals(NurbsType.OPEN, direction.getType());
        assertEquals(4, direction.getCount());
    }