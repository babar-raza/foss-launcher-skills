public static byte[] Ico(int width, int height, int bitCount = 32, int imageCount = 1) =>
        new ByteBuilder()
            .Bytes(0, 0, 1, 0)
            .UInt16LE(imageCount)
            .Bytes((byte)width, (byte)height, 0, 0)
            .UInt16LE(1)
            .UInt16LE(bitCount)
            .UInt32LE(0)
            .UInt32LE(22)
            .ToArray();