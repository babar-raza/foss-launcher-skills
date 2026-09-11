public static byte[] WebPExtended(int width, int height) =>
        new ByteBuilder()
            .Ascii("RIFF")
            .UInt32LE(0)
            .Ascii("WEBP")
            .Ascii("VP8X")
            .UInt32LE(10)
            .Bytes(0)
            .Zeros(3)
            .UInt24LE(width - 1)
            .UInt24LE(height - 1)
            .ToArray();