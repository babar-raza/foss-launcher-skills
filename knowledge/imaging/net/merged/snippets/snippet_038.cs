public static byte[] TiffWithPages(int width, int height, int bitDepth, int pageCount)
    {
        const int entryCount = 3;
        const int ifdSize = 2 + entryCount * 12 + 4; // count + entries + next-IFD offset
        const int firstIfdOffset = 8;

        var builder = new ByteBuilder()
            .Ascii("II")
            .Bytes(0x2A, 0x00)
            .UInt32LE(firstIfdOffset);

        for (var page = 0; page < pageCount; page++)
        {
            builder.UInt16LE(entryCount);
            AddShortEntry(builder, 256, width);
            AddShortEntry(builder, 257, height);
            AddShortEntry(builder, 258, bitDepth);

            var isLast = page == pageCount - 1;
            var nextOffset = isLast ? 0u : (uint)(firstIfdOffset + (page + 1) * ifdSize);
            builder.UInt32LE(nextOffset);
        }

        return builder.ToArray();
    }