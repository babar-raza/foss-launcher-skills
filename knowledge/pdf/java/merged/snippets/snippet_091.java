@Test
    public void testContains() {
        assertTrue(AdobeGlyphList.contains("bullet"));
        assertTrue(AdobeGlyphList.contains("A"));
        assertFalse(AdobeGlyphList.contains("doesNotExist"));
        assertFalse(AdobeGlyphList.contains(null));
    }