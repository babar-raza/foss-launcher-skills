@Test
    public void shiftImageMatchesScalar() {
        java.awt.image.BufferedImage img = new java.awt.image.BufferedImage(
                2, 1, java.awt.image.BufferedImage.TYPE_INT_RGB);
        img.setRGB(0, 0, 0xC110A0);
        img.setRGB(1, 0, 0xFFB81C);
        RgbPrintShift.shiftImage(img);
        assertEquals(RgbPrintShift.shift(0xFFC110A0) & 0xFFFFFF, img.getRGB(0, 0) & 0xFFFFFF);
        assertEquals(RgbPrintShift.shift(0xFFFFB81C) & 0xFFFFFF, img.getRGB(1, 0) & 0xFFFFFF);
    }