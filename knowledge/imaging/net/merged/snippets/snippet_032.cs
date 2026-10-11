public static byte[] Bmp(int width, int height, int bitCount = 24) =>
        new ByteBuilder()
            .Ascii("BM")
            .UInt32LE(0)
            .UInt32LE(0)
            .UInt32LE(54)
            .UInt32LE(40)
            .Int32LE(width)
            .Int32LE(height)
            .UInt16LE(1)
            .UInt16LE(bitCount)
            .ToArray();