private static byte[] deflate(byte[] raw) {
        Deflater deflater = new Deflater();
        deflater.setInput(raw);
        deflater.finish();
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] buf = new byte[8192];
        while (!deflater.finished()) {
            out.write(buf, 0, deflater.deflate(buf));
        }
        deflater.end();
        return out.toByteArray();
    }