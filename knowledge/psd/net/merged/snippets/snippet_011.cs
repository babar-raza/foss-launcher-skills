[Test]
    public void Load_IndexedData_ParsesPalette()
    {
        byte[] payload = BuildIndexedPalettePayload();
        using var stream = new MemoryStream(BuildColorDataSection(payload));
        using var reader = new BigEndianReader(stream, leaveOpen: true);

        ColorData colorData = ColorData.Load(reader, ColorModes.Indexed);

        Assert.That(colorData.Kind, Is.EqualTo(PsdColorDataKind.IndexedPalette));
        Assert.That(colorData.RawData, Is.EqualTo(payload));
        Assert.That(colorData.IndexedPalette, Is.Not.Null);
        Assert.That(colorData.IndexedPalette!.Entries, Has.Length.EqualTo(256));
        Assert.That(colorData.IndexedPalette.Entries[0], Is.EqualTo(System.Drawing.Color.FromArgb(0x00, 0xFF, 0x80)));
        Assert.That(colorData.IndexedPalette.Entries[17], Is.EqualTo(System.Drawing.Color.FromArgb(0x11, 0xEE, 0x91)));
    }