@Test
    void enumValues_matchSpecBits() {
        assertEquals(1,   AnnotationFlags.Invisible.getBit());
        assertEquals(2,   AnnotationFlags.Hidden.getBit());
        assertEquals(4,   AnnotationFlags.Print.getBit());
        assertEquals(8,   AnnotationFlags.NoZoom.getBit());
        assertEquals(16,  AnnotationFlags.NoRotate.getBit());
        assertEquals(32,  AnnotationFlags.NoView.getBit());
        assertEquals(64,  AnnotationFlags.ReadOnly.getBit());
        assertEquals(128, AnnotationFlags.Locked.getBit());
        assertEquals(256, AnnotationFlags.ToggleNoView.getBit());
        assertEquals(512, AnnotationFlags.LockedContents.getBit());
    }