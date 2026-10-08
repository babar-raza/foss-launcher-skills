@Test
    void propertyArbitraryJulLevel_works() {
        System.setProperty(AsposePdfLogging.LOG_PROPERTY, "SEVERE");
        AsposePdfLogging.configureFromSystemProperty();
        assertEquals(Level.SEVERE, AsposePdfLogging.getLevel());
    }