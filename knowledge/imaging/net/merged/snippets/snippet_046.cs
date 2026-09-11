private static void AppendTransferSyntax(ByteBuilder builder, string uid)
    {
        var padded = uid.Length % 2 == 0 ? uid : uid + "\0";
        builder.UInt16LE(0x0002).UInt16LE(0x0010).Ascii("UI").UInt16LE(padded.Length).Ascii(padded);
    }