@Test
    public void nullResolutionThrows() {
        assertThrows(IllegalArgumentException.class, () -> new TiffDevice((Resolution) null));
    }