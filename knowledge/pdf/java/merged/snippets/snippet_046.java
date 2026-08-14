@Test
    void propertyWarning_enablesWarning() {
        System.setProperty(AsposePdfLogging.LOG_PROPERTY, "warning");
        AsposePdfLogging.configureFromSystemProperty();
        assertEquals(Level.WARNING, AsposePdfLogging.getLevel());
    }