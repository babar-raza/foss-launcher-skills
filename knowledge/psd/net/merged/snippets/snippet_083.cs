protected static byte[] BuildImageDataSection(CompressionMethod compression, byte[] payload)
    {
        using var stream = new MemoryStream();
        using var writer = new BigEndianWriter(stream, leaveOpen: true);
        writer.Write((ushort)compression);
        writer.Write(payload);
        return stream.ToArray();
    }