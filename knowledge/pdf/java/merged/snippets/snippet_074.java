@Test
    void propertyOn_enablesWarning() {
        System.setProperty(AsposePdfLogging.LOG_PROPERTY, "on");
        AsposePdfLogging.configureFromSystemProperty();
        assertEquals(Level.WARNING, AsposePdfLogging.getLevel());
    }