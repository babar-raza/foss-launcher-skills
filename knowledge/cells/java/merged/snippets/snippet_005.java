private static void saveWorkbook(Workbook wb, Path path) throws IOException {
        if (!Files.exists(path)) { Files.createDirectories(path.getParent()); wb.save(path.toString()); }
    }