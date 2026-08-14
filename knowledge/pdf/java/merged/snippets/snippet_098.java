@Test
    void styledRequestStillEmbedsAvailableFace(@TempDir Path dir) throws Exception {
        // only a regular face exists; a bold request must still resolve *a* face (last-resort fallback).
        Files.write(dir.resolve("testfont.ttf"), fixtureTtf());
        byte[] bold = FontDiskLookup.loadStyled("TestFont", true, false, new String[]{dir.toString()});
        assertNotNull(bold, "bold request falls back to the available regular face");
    }