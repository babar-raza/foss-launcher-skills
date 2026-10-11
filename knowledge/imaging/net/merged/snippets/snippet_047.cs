private static void AppendExplicitUShort(ByteBuilder builder, int group, int element, int value) =>
        builder.UInt16LE(group).UInt16LE(element).Ascii("US").UInt16LE(2).UInt16LE(value);