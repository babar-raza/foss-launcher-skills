@Test
    void toBits_encodes() {
        assertEquals(0, AnnotationFlags.toBits(EnumSet.noneOf(AnnotationFlags.class)));
        assertEquals(4, AnnotationFlags.toBits(EnumSet.of(AnnotationFlags.Print)));
        assertEquals(4 | 64,
                AnnotationFlags.toBits(EnumSet.of(AnnotationFlags.Print, AnnotationFlags.ReadOnly)));
    }