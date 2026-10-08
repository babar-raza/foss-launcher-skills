@Test
    public void nullListThrows() {
        assertThrows(IllegalArgumentException.class, () -> new OperatorCollection(null));
    }