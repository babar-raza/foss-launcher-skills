@Test
    public void capDefaultsAndDisable() {
        System.clearProperty(DecodeLimits.PROPERTY);
        assertEquals(DecodeLimits.DEFAULT_MAX_DECODED_BYTES, DecodeLimits.maxDecodedBytes());
        setCap(0); // <= 0 disables the guard
        assertEquals(Long.MAX_VALUE, DecodeLimits.maxDecodedBytes());
        setCap(12345);
        assertEquals(12345, DecodeLimits.maxDecodedBytes());
    }