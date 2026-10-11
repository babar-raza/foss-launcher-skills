[Test]
    public void Load_DocumentDtos_ReadValues()
    {
        using var image = PsdImage.Load(Path.Combine(TestContext.CurrentContext.TestDirectory, "testdata", "test.psd"));

        Assert.That(image.Resources, Has.Count.EqualTo(26));
        Assert.That(image.Resources[0].Kind, Is.EqualTo(PsdResourceKind.Unknown));
        Assert.That(image.Resources[1].Kind, Is.EqualTo(PsdResourceKind.Unknown));
        Assert.That(image.Resources[2].Kind, Is.EqualTo(PsdResourceKind.Unknown));
        Assert.That(image.Resources[0].GlobalAngle, Is.Null);
        Assert.That(image.Resources[1].GlobalAngle, Is.Null);
        Assert.That(image.Resources[2].GlobalAngle, Is.Null);
        Assert.That(image.HasIccProfile, Is.False);
        Assert.That(image.IsIccProfileUntagged, Is.Null);
        Assert.That(image.GlobalAngle, Is.EqualTo(0));

        Assert.That(image.ColorDataInfo.Kind, Is.EqualTo(PsdColorDataKind.None));
        Assert.That(image.ColorDataInfo.RawDataLength, Is.EqualTo(0));
        Assert.That(image.IndexedPalette, Is.Null);

        Assert.That(image.ImageDataInfo.Kind, Is.EqualTo(ImageDataKind.Rle));
        Assert.That(image.ImageDataInfo.RowLengthFieldSize, Is.EqualTo(sizeof(ushort)));
        Assert.That(image.ImageDataInfo.RowByteCounts, Has.Count.EqualTo(300));
        Assert.That(image.ImageDataInfo.CompressedPayloadLength, Is.GreaterThan(0));
        Assert.That(image.ImageDataInfo.UsesPrediction, Is.False);
    }