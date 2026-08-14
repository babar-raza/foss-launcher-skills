@Test
    void warning_allowsChildWarningButNotFine() {
        AsposePdfLogging.setLevel(Level.WARNING);
        Logger child = Logger.getLogger("org.aspose.pdf.engine.parser.PDFParser");
        assertTrue(child.isLoggable(Level.WARNING),
                "At WARNING level, engine warnings should pass");
        assertFalse(child.isLoggable(Level.FINE),
                "At WARNING level, recovery FINE detail should still be suppressed");
    }