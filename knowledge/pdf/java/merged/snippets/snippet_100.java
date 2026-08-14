@Test
    void syntheticTtfParses() throws Exception {
        byte[] ttf = MinimalTtf.build("TestFont", glyphs());
        TrueTypeReader r = new TrueTypeReader(ttf);
        assertEquals(1000, r.getUnitsPerEm(), "unitsPerEm");
        assertEquals(3, r.getNumGlyphs(), ".notdef + A + B");
        assertEquals(1, r.getGlyphId('A'), "cmap A→gid1");
        assertEquals(2, r.getGlyphId('B'), "cmap B→gid2");
        assertEquals(700, r.getAdvanceWidth(1), "hmtx A advance");
        assertEquals(800, r.getAdvanceWidth(2), "hmtx B advance");
    }