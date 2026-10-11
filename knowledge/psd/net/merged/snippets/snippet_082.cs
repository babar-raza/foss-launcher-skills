protected static byte[] BuildColorDataSection(byte[] payload)
    {
        using var stream = new MemoryStream();
        using var writer = new BigEndianWriter(stream, leaveOpen: true);
        writer.Write((uint)payload.Length);
        writer.Write(payload);
        return stream.ToArray();
    }