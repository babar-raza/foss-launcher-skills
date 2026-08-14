@Test
    void rejectsOversizePayload() {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < 4000; i++) {
            sb.append('X');
        }
        assertThrows(IllegalArgumentException.class,
                () -> QrEncoder.encodeBytes(sb.toString().getBytes(), QrEncoder.Ecc.HIGH));
    }