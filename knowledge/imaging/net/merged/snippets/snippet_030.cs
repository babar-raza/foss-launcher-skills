public static byte[] GifWithFrames(int width, int height, int frameCount)
    {
        var builder = new ByteBuilder()
            .Ascii("GIF89a")
            .UInt16LE(width)
            .UInt16LE(height)
            .Bytes(0, 0, 0); // packed fields (no global color table), bg color index, aspect ratio

        for (var i = 0; i < frameCount; i++)
        {
            builder
                .Bytes(ImageDescriptorIntroducer)
                .UInt16LE(0).UInt16LE(0) // left, top
                .UInt16LE(width).UInt16LE(height)
                .Bytes(0) // packed fields (no local color table)
                .Bytes(2) // LZW minimum code size
                .Bytes(1, 0x00, 0); // one data sub-block, then the terminator
        }

        builder.Bytes(GifTrailer);
        return builder.ToArray();
    }