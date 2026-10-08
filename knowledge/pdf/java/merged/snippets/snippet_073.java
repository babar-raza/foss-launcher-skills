@Test
    void default_isOff() {
        System.clearProperty(AsposePdfLogging.LOG_PROPERTY);
        AsposePdfLogging.configureFromSystemProperty();
        assertEquals(Level.OFF, AsposePdfLogging.getLevel());
    }