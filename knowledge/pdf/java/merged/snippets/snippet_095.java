@Test
    void resolvesFamilyInConfiguredDir(@TempDir Path dir) throws Exception {
        Files.write(dir.resolve("testfont.ttf"), fixtureTtf());
        byte[] found = FontDiskLookup.loadStyled("TestFont", false, false, new String[]{dir.toString()});
        assertNotNull(found, "family resolved from the configured dir");
        // parses back to the same font
        assertTrue(new TrueTypeReader(found).getNumGlyphs() >= 2, "resolved bytes are a valid TTF");
    }