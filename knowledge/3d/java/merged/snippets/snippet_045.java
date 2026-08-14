@Test
    public void type_ShouldBeSettable() {
        NurbsDirection direction = new NurbsDirection();
        direction.setType(NurbsType.CLOSED);

        assertEquals(NurbsType.CLOSED, direction.getType());
    }