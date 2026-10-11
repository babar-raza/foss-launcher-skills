@Test
    void verbose_allowsChildFine() {
        AsposePdfLogging.setLevel(Level.FINE);
        Logger child = Logger.getLogger("org.aspose.pdf.engine.parser.PDFParser");
        assertTrue(child.isLoggable(Level.FINE),
                "At verbose/FINE level, recovery details should pass");
    }