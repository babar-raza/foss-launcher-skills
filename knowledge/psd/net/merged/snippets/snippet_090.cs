protected static byte[] BuildPsbLayerRecordBytes()
    {
        using var stream = new MemoryStream();
        using var writer = new BigEndianWriter(stream, leaveOpen: true);

        writer.Write(0);
        writer.Write(0);
        writer.Write(1);
        writer.Write(1);
        writer.Write((ushort)4);
        writer.Write((short)-1);
        writer.Write((ulong)3);
        writer.Write((short)0);
        writer.Write((ulong)3);
        writer.Write((short)1);
        writer.Write((ulong)3);
        writer.Write((short)2);
        writer.Write((ulong)3);
        writer.Write(0x3842494D);
        writer.Write(System.Text.Encoding.ASCII.GetBytes("norm"));
        writer.Write((byte)200);
        writer.Write((byte)0);
        writer.Write((byte)0);
        writer.Write((byte)0);

        using var extraDataStream = new MemoryStream();
        using var extraDataWriter = new BigEndianWriter(extraDataStream, leaveOpen: true);
        extraDataWriter.Write((uint)0);
        extraDataWriter.Write((uint)0);
        extraDataWriter.WritePascalString("Layer 1");

        byte[] extraData = extraDataStream.ToArray();
        writer.Write(extraData.Length);
        writer.Write(extraData);

        return stream.ToArray();
    }