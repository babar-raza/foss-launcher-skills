@Test
    void off_suppressesChildLoggerWarning() {
        AsposePdfLogging.setLevel(Level.OFF);
        Logger child = Logger.getLogger("org.aspose.pdf.engine.parser.PDFParser");
        assertFalse(child.isLoggable(Level.WARNING),
                "With library logging OFF, an engine WARNING must be suppressed");
        assertFalse(child.isLoggable(Level.SEVERE),
                "With library logging OFF, even SEVERE is suppressed");
    }