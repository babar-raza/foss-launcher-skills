[Test]
    public void Load_RleFixture_ReadsImageData()
    {
        using var image = PsdImage.Load(GetTestDataPath("rle.psd"));

        Assert.That(image.Compression, Is.EqualTo(CompressionMethod.RLE));
        Assert.That(image.ImageDataKind, Is.EqualTo(ImageDataKind.Rle));
        Assert.That(image.ImageDataInfo.RowLengthFieldSize, Is.EqualTo(sizeof(ushort)));
        Assert.That(image.ImageDataInfo.RowByteCounts, Has.Count.EqualTo(600));
        Assert.That(image.ImageDataInfo.CompressedPayloadLength, Is.EqualTo(5219));
    }