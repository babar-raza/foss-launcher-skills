@Test
    public void degree_ShouldBeSettable() {
        NurbsDirection direction = new NurbsDirection();
        direction.setDegree(2);

        assertEquals(2, direction.getDegree());
    }