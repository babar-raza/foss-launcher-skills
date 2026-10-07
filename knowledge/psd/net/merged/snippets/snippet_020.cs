[Test]
    public void Load_BasicPsb_ReadsMetadata()
    {
        using var image = PsdImage.Load(GetTestDataPath("basic.psb"));

        Assert.That(image.Version, Is.EqualTo(6));
        Assert.That(image.Header.Version, Is.EqualTo(PsdHeader.PsbVersion));
        Assert.That(image.IsLargeDocument, Is.True);
        Assert.That(image.IsPsb, Is.True);
        Assert.That(image.Width, Is.EqualTo(200));
        Assert.That(image.Height, Is.EqualTo(200));
        Assert.That(image.LayerCount, Is.EqualTo(0));
        Assert.That(image.ResourceCount, Is.EqualTo(24));
        Assert.That(image.Compression, Is.EqualTo(CompressionMethod.RLE));
        Assert.That(image.ImageDataInfo.RowLengthFieldSize, Is.EqualTo(sizeof(uint)));
    }