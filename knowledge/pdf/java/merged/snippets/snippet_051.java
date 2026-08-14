@Test
    void setLevelNull_silencesLibrary() {
        AsposePdfLogging.setLevel(Level.WARNING);
        AsposePdfLogging.setLevel(null);
        assertEquals(Level.OFF, AsposePdfLogging.getLevel());
    }