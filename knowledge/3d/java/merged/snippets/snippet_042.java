@Test
    public void order_ShouldBeSettable() {
        NurbsDirection direction = new NurbsDirection();
        direction.setOrder(4);

        assertEquals(4, direction.getOrder());
    }