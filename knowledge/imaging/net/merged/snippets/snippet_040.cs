private static void AddShortEntry(ByteBuilder builder, int tag, int value)
    {
        builder.UInt16LE(tag);
        builder.UInt16LE(3);
        builder.UInt32LE(1);
        builder.UInt16LE(value);
        builder.UInt16LE(0);
    }