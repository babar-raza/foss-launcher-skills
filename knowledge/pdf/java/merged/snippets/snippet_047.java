@Test
    void propertyVerbose_enablesFine() {
        System.setProperty(AsposePdfLogging.LOG_PROPERTY, "verbose");
        AsposePdfLogging.configureFromSystemProperty();
        assertEquals(Level.FINE, AsposePdfLogging.getLevel());
    }