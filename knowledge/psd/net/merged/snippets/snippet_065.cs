[Test]
    public void Load_DocInspection_Reads()
    {
        using var image = PsdImage.Load(Path.Combine(TestContext.CurrentContext.TestDirectory, "testdata", "test.psd"));

        Assert.That(image.Header, Is.Not.Null);
        Assert.That(image.IsLargeDocument, Is.False);
        Assert.That(image.IsPsb, Is.False);
        Assert.That(image.LayerCount, Is.EqualTo(2));
        Assert.That(image.HasImageResources, Is.True);
        Assert.That(image.ResourceCount, Is.EqualTo(26));
        Assert.That(image.HasColorModeData, Is.False);
        Assert.That(image.HasMergedImageData, Is.True);
        Assert.That(image.Compression, Is.EqualTo(CompressionMethod.RLE));
        Assert.That(image.ImageDataKind, Is.EqualTo(ImageDataKind.Rle));
        Assert.That(image.UsesPrediction, Is.False);
        Assert.That(image.Version, Is.EqualTo(6));
        Assert.That(image.Header.Version, Is.EqualTo(PsdHeader.PsdVersion));
        Assert.That(image.Header.ColorMode, Is.EqualTo(image.ColorMode));
    }