public static byte[] WebPLossy(int width, int height) =>
        new ByteBuilder()
            .Ascii("RIFF")
            .UInt32LE(0)
            .Ascii("WEBP")
            .Ascii("VP8 ")
            .UInt32LE(10)
            .Bytes(0, 0, 0)
            .Bytes(0x9d, 0x01, 0x2a)
            .UInt16LE(width & 0x3FFF)
            .UInt16LE(height & 0x3FFF)
            .ToArray();