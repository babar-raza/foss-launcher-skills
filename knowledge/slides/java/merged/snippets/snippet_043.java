private static byte[] createTestPng(int r, int g, int b) throws IOException {
        BufferedImage buffered = new BufferedImage(10, 10, BufferedImage.TYPE_INT_ARGB);
        int argb = (255 << 24) | (r << 16) | (g << 8) | b;
        for (int y = 0; y < 10; y++) {
            for (int x = 0; x < 10; x++) {
                buffered.setRGB(x, y, argb);
            }
        }
        ByteArrayOutputStream baos = new ByteArrayOutputStream();
        ImageIO.write(buffered, "png", baos);
        return baos.toByteArray();
    }