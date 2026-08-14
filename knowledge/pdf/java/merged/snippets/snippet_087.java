@Test
    public void smallStreamsDecodeNormallyUnderCap() throws Exception {
        setCap(TEST_CAP);
        byte[] raw = "Hello, ISO 32000! ".repeat(100).getBytes("US-ASCII");
        assertArrayEquals(raw, new FlateFilter().decode(deflate(raw), null),
                "flate round-trip under cap");
        RunLengthFilter rl = new RunLengthFilter();
        assertArrayEquals(raw, rl.decode(rl.encode(raw, null), null),
                "run-length round-trip under cap");
        // LZWFilter is decode-only (encode throws "use FlateDecode") — its
        // cap shares DecodeLimits.check with the two filters tested above.
    }