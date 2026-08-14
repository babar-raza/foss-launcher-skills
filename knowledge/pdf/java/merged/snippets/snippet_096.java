@Test
    void emptyDirFallsThroughToNull(@TempDir Path dir) {
        byte[] found = FontDiskLookup.loadStyled("TotallyUnknownFamily12345", false, false,
                new String[]{dir.toString()});
        assertNull(found, "no font in dir and not on host → null (clean fallback)");
    }