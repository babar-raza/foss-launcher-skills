[Test]
    public void Load_RgbPayload_Classifies()
    {
        byte[] payload = [0x10, 0x20, 0x30, 0x40];
        using var stream = new MemoryStream(BuildColorDataSection(payload));
        using var reader = new BigEndianReader(stream, leaveOpen: true);

        ColorData colorData = ColorData.Load(reader, ColorModes.Rgb);

        Assert.That(colorData.Kind, Is.EqualTo(PsdColorDataKind.RgbPayload));
        Assert.That(colorData.RawData, Is.EqualTo(payload));
        Assert.That(colorData.IndexedPalette, Is.Null);
    }