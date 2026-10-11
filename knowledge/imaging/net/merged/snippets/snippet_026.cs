public static byte[] Png(int width, int height, int bitDepth = 8) =>
        new ByteBuilder()
            .Bytes(0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A)
            .UInt32BE(13)
            .Ascii("IHDR")
            .UInt32BE((uint)width)
            .UInt32BE((uint)height)
            .Bytes((byte)bitDepth, 2, 0, 0, 0)
            .Zeros(4)
            .ToArray();