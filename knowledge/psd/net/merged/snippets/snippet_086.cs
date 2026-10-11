protected static byte[] BuildLayerRecordBytesWithExtraData(byte[] extraData)
    {
        using var stream = new MemoryStream();
        using var writer = new BigEndianWriter(stream, leaveOpen: true);

        writer.Write(0);
        writer.Write(0);
        writer.Write(1);
        writer.Write(1);
        writer.Write((ushort)0);
        writer.Write(0x3842494D);
        writer.Write(System.Text.Encoding.ASCII.GetBytes("norm"));
        writer.Write((byte)255);
        writer.Write((byte)0);
        writer.Write((byte)0);
        writer.Write((byte)0);
        writer.Write(extraData.Length);
        writer.Write(extraData);

        return stream.ToArray();
    }