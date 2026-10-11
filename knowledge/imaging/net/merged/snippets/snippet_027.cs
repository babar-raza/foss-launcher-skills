public static byte[] Jpeg(int width, int height, int precision = 8) =>
        new ByteBuilder()
            .Bytes(0xFF, 0xD8, 0xFF, 0xC0)
            .UInt16BE(7)
            .Bytes((byte)precision)
            .UInt16BE(height)
            .UInt16BE(width)
            .ToArray();