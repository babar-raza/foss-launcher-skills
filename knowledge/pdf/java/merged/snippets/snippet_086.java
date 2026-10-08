private static String string(PdfBase value) {
        return value == null ? null : ((PdfString) value).getString();
    }