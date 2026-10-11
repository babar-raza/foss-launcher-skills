@Test
    public void divisions_ShouldBeSettable() {
        NurbsDirection direction = new NurbsDirection();
        direction.setDivisions(20);

        assertEquals(20, direction.getDivisions());
    }