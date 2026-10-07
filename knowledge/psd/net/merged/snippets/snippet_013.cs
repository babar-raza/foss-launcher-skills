[Test]
    public void Load_IndexedFixture_ReadsData()
    {
        using var image = PsdImage.Load(GetTestDataPath("basic-indexed.psd"));

        Assert.That(image.Width, Is.EqualTo(200));
        Assert.That(image.Height, Is.EqualTo(200));
        Assert.That(image.Channels, Is.EqualTo(1));
        Assert.That(image.ColorMode, Is.EqualTo(ColorModes.Indexed));
        Assert.That(image.HasColorModeData, Is.True);
        Assert.That(image.ColorDataInfo.Kind, Is.EqualTo(PsdColorDataKind.IndexedPalette));
        Assert.That(image.ColorDataInfo.RawDataLength, Is.EqualTo(768));
        Assert.That(image.LayerCount, Is.EqualTo(0));
        Assert.That(image.ResourceCount, Is.EqualTo(24));
    }