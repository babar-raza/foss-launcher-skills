[Test]
    public void Load_BasicRgb_ReadsMetadata()
    {
        using var image = PsdImage.Load(GetTestDataPath("basic-rgb.psd"));

        Assert.That(image.Width, Is.EqualTo(200));
        Assert.That(image.Height, Is.EqualTo(200));
        Assert.That(image.Channels, Is.EqualTo(3));
        Assert.That(image.BitsPerChannel, Is.EqualTo(8));
        Assert.That(image.ColorMode, Is.EqualTo(ColorModes.Rgb));
        Assert.That(image.Version, Is.EqualTo(6));
        Assert.That(image.Header.Version, Is.EqualTo(PsdHeader.PsdVersion));
        Assert.That(image.LayerCount, Is.EqualTo(3));
        Assert.That(image.ResourceCount, Is.EqualTo(26));
        Assert.That(image.Compression, Is.EqualTo(CompressionMethod.RLE));
    }