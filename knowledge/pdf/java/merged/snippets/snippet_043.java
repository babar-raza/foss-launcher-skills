@AfterEach
    void resetToSilent() {
        // Leave the shared JUL state silent so other test classes in the same
        // fork are unaffected.
        System.clearProperty(AsposePdfLogging.LOG_PROPERTY);
        AsposePdfLogging.configureFromSystemProperty();
    }