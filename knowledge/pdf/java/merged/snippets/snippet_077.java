@Test
    void propertyDebug_enablesAll() {
        System.setProperty(AsposePdfLogging.LOG_PROPERTY, "debug");
        AsposePdfLogging.configureFromSystemProperty();
        assertEquals(Level.ALL, AsposePdfLogging.getLevel());
    }