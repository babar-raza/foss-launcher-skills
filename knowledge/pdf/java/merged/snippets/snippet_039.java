@Test
    void fromBits_returnsCorrectFlags() {
        EnumSet<AnnotationFlags> empty = AnnotationFlags.fromBits(0);
        assertTrue(empty.isEmpty());

        EnumSet<AnnotationFlags> printOnly = AnnotationFlags.fromBits(4);
        assertEquals(EnumSet.of(AnnotationFlags.Print), printOnly);

        EnumSet<AnnotationFlags> mixed = AnnotationFlags.fromBits(4 | 64); // Print + ReadOnly
        assertEquals(EnumSet.of(AnnotationFlags.Print, AnnotationFlags.ReadOnly), mixed);

        EnumSet<AnnotationFlags> all = AnnotationFlags.fromBits(0x3FF);
        assertEquals(10, all.size());
    }