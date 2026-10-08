@Test
    void propertyInvalid_fallsBackToOff() {
        System.setProperty(AsposePdfLogging.LOG_PROPERTY, "garbage");
        AsposePdfLogging.configureFromSystemProperty();
        assertEquals(Level.OFF, AsposePdfLogging.getLevel());
    }