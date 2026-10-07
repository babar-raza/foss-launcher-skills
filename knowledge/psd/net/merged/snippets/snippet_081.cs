protected static byte[] BuildHeaderBytes(
        ushort version,
        ushort channels = 3,
        int width = 1,
        int height = 1,
        ushort bitDepth = 8,
        ColorModes colorMode = ColorModes.Rgb)
    {
        using var stream = new MemoryStream();
        using var writer = new BigEndianWriter(stream, leaveOpen: true);

        stream.Write(System.Text.Encoding.ASCII.GetBytes("8BPS"));
        writer.Write(version);
        writer.Write(new byte[6]);
        writer.Write(channels);
        writer.Write(height);
        writer.Write(width);
        writer.Write(bitDepth);
        writer.Write((ushort)colorMode);

        return stream.ToArray();
    }