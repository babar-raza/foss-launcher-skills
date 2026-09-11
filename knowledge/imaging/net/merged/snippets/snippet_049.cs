private static void AppendImplicitUShort(ByteBuilder builder, int group, int element, int value) =>
        builder.UInt16LE(group).UInt16LE(element).UInt32LE(2).UInt16LE(value);