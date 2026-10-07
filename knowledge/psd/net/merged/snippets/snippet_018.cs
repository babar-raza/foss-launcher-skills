[Test]
    public void Load_BasicCmyk_ReadsMetadata()
    {
        using var image = PsdImage.Load(GetTestDataPath("basic-cmyk.psd"));

        Assert.That(image.Width, Is.EqualTo(200));
        Assert.That(image.Height, Is.EqualTo(200));
        Assert.That(image.Channels, Is.EqualTo(4));
        Assert.That(image.ColorMode, Is.EqualTo(ColorModes.Cmyk));
        Assert.That(image.LayerCount, Is.EqualTo(3));
        Assert.That(image.ResourceCount, Is.EqualTo(28));
        Assert.That(image.Compression, Is.EqualTo(CompressionMethod.RLE));
        Assert.That(image.ImageDataInfo.RowByteCounts, Has.Count.EqualTo(800));
    }