[Test]
    public void Load_PsdZip_ReadsStructure()
    {
        using var stream = new MemoryStream(BuildImageDataSection(CompressionMethod.ZipWithoutPrediction, [0x78, 0x9C, 0x63, 0x60, 0x04, 0x00, 0x00, 0xFF, 0x00]));
        using var reader = new BigEndianReader(stream, leaveOpen: true);

        ImageData imageData = ImageData.Load(reader, isLargeDocument: false, height: 1, channelCount: 3);

        Assert.That(imageData.Compression, Is.EqualTo(CompressionMethod.ZipWithoutPrediction));
        Assert.That(imageData.Structure.Kind, Is.EqualTo(ImageDataKind.Zip));
        Assert.That(imageData.Structure.UsesPrediction, Is.False);
        Assert.That(imageData.Structure.CompressedPayloadLength, Is.EqualTo(9));
    }