@Test
    void testDisposeIsIdempotent() {
        Presentation pres = new Presentation();
        pres.dispose();
        pres.dispose(); // second call should be harmless
    }