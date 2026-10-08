@Test
    void unknownBits_ignored() {
        EnumSet<AnnotationFlags> high = AnnotationFlags.fromBits(0x40000); // bit 19, unmapped
        assertTrue(high.isEmpty());
    }