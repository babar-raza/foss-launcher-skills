private static void writeBytes(Path path, byte[] data) throws IOException {
        if (!Files.exists(path)) { Files.createDirectories(path.getParent()); Files.write(path, data); }
    }