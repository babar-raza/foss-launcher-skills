public static byte[] WebPLossless(int width, int height)
    {
        var packed = (uint)((width - 1) & 0x3FFF) | (uint)(((height - 1) & 0x3FFF) << 14);
        return new ByteBuilder()
            .Ascii("RIFF")
            .UInt32LE(0)
            .Ascii("WEBP")
            .Ascii("VP8L")
            .UInt32LE(5)
            .Bytes(0x2F)
            .UInt32LE(packed)
            .ToArray();
    }