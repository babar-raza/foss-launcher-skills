private static void writePoi(XSSFWorkbook wb, Path path) throws IOException {
        if (!Files.exists(path)) { Files.createDirectories(path.getParent());
            try (OutputStream os = Files.newOutputStream(path)) { wb.write(os); } }
    }