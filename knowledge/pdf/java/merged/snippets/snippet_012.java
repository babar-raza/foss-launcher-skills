@Test
    void roundTrip_bitsEnumBits() {
        int original = 1 | 4 | 64 | 256; // Invisible + Print + ReadOnly + ToggleNoView
        EnumSet<AnnotationFlags> set = AnnotationFlags.fromBits(original);
        assertEquals(original, AnnotationFlags.toBits(set));
    }