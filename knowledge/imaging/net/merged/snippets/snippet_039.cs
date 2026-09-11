public static byte[] TiffWithSelfReferencingIfd(int width, int height, int bitDepth)
    {
        const int entryCount = 3;
        const int firstIfdOffset = 8;

        var builder = new ByteBuilder()
            .Ascii("II")
            .Bytes(0x2A, 0x00)
            .UInt32LE(firstIfdOffset)
            .UInt16LE(entryCount);

        AddShortEntry(builder, 256, width);
        AddShortEntry(builder, 257, height);
        AddShortEntry(builder, 258, bitDepth);

        builder.UInt32LE(firstIfdOffset); // next-IFD offset points back at the same IFD

        return builder.ToArray();
    }