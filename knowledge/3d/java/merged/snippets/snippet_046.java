@Test
    public void count_ShouldBeSettable() {
        NurbsDirection direction = new NurbsDirection();
        direction.setCount(8);

        assertEquals(8, direction.getCount());
    }