private static void setCap(long bytes) {
        System.setProperty(DecodeLimits.PROPERTY, Long.toString(bytes));
    }