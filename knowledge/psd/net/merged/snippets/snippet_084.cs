protected static byte[] BuildIndexedPalettePayload()
    {
        byte[] payload = new byte[IndexedColorPalette.ExpectedRawLength];
        for (int i = 0; i < 256; i++)
        {
            payload[i] = (byte)i;
            payload[i + 256] = (byte)(255 - i);
            payload[i + 512] = (byte)(128 + (i % 64));
        }

        return payload;
    }