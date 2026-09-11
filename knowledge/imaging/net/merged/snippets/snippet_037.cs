public static byte[] Tiff(int width, int height, int bitDepth = 8) =>
        TiffWithPages(width, height, bitDepth, pageCount: 1);