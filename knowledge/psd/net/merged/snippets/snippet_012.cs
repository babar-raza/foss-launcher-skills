[Test]
    public void Load_CmykPayload_Classifies()
    {
        byte[] payload = [0xCA, 0xFE, 0xBA, 0xBE];
        using var stream = new MemoryStream(BuildColorDataSection(payload));
        using var reader = new BigEndianReader(stream, leaveOpen: true);

        ColorData colorData = ColorData.Load(reader, ColorModes.Cmyk);

        Assert.That(colorData.Kind, Is.EqualTo(PsdColorDataKind.CmykPayload));
        Assert.That(colorData.RawData, Is.EqualTo(payload));
        Assert.That(colorData.IndexedPalette, Is.Null);
    }