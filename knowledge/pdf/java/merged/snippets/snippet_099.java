@Test
    public void runLengthBombIsRejectedAtCap() {
        setCap(TEST_CAP);
        // Each pair (0x81, X) expands to 128 bytes; 32k pairs = 4 MB decoded.
        byte[] bomb = new byte[32 * 1024 * 2];
        for (int i = 0; i < bomb.length; i += 2) {
            bomb[i] = (byte) 0x81; // 257-129 = 128 repeats
            bomb[i + 1] = 'A';
        }
        IOException e = assertThrows(IOException.class,
                () -> new RunLengthFilter().decode(bomb, null));
        assertTrue(e.getMessage().contains("exceeds"),
                "cap diagnostics expected, got: " + e.getMessage());
    }