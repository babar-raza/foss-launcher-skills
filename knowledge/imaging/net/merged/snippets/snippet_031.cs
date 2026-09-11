public static byte[] GifWithoutFrames(int width, int height) =>
        new ByteBuilder()
            .Ascii("GIF89a")
            .UInt16LE(width)
            .UInt16LE(height)
            .Bytes(0, 0, 0)
            .ToArray();