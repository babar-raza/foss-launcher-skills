protected static byte[] BuildResourcesPayload(params (short resourceId, string name, byte[] data)[] resources)
    {
        using var stream = new MemoryStream();

        void WriteInt16(short value)
        {
            stream.WriteByte((byte)(value >> 8));
            stream.WriteByte((byte)value);
        }

        void WriteInt32(int value)
        {
            stream.WriteByte((byte)(value >> 24));
            stream.WriteByte((byte)(value >> 16));
            stream.WriteByte((byte)(value >> 8));
            stream.WriteByte((byte)value);
        }

        foreach ((short resourceId, string name, byte[] data) in resources)
        {
            stream.Write(System.Text.Encoding.ASCII.GetBytes("8BIM"));
            WriteInt16(resourceId);

            byte[] nameBytes = System.Text.Encoding.ASCII.GetBytes(name);
            stream.WriteByte((byte)nameBytes.Length);
            stream.Write(nameBytes);
            if ((nameBytes.Length + 1) % 2 != 0)
            {
                stream.WriteByte(0);
            }

            WriteInt32(data.Length);
            stream.Write(data);
            if (data.Length % 2 == 1)
            {
                stream.WriteByte(0);
            }
        }

        return stream.ToArray();
    }