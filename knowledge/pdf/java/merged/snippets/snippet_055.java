@Test
    void doesNotTouchRootLogger() {
        AsposePdfLogging.setLevel(Level.FINE);
        // The library must not alter the JUL root logger's level.
        Logger root = Logger.getLogger("");
        assertNotSame(Logger.getLogger("org.aspose.pdf"), root);
        // org.aspose.pdf must not propagate to root handlers.
        assertFalse(Logger.getLogger("org.aspose.pdf").getUseParentHandlers(),
                "Library logger must not use parent (root) handlers");
    }