@Test
    public void flateBombIsRejectedAtCap() {
        setCap(TEST_CAP);
        byte[] bomb = deflate(new byte[4 << 20]);
        assertTrue(bomb.length < 64 * 1024, "bomb must be small encoded");
        IOException e = assertThrows(IOException.class,
                () -> new FlateFilter().decode(bomb, null));
        assertTrue(e.getMessage().contains("exceeds"),
                "cap diagnostics expected, got: " + e.getMessage());
    }