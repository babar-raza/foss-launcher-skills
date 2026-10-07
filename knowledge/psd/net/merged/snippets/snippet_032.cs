[Test]
    public void Load_PsdRle_ReadsStructure()
    {
        using var stream = new MemoryStream(BuildImageDataSection(CompressionMethod.RLE, [0x00, 0x02, 0xAB, 0xCD, 0x00, 0x01, 0xEF]));
        using var reader = new BigEndianReader(stream, leaveOpen: true);

        ImageData imageData = ImageData.Load(reader, isLargeDocument: false, height: 1, channelCount: 3);

        Assert.That(imageData.Compression, Is.EqualTo(CompressionMethod.RLE));
        Assert.That(imageData.Structure.Kind, Is.EqualTo(ImageDataKind.Rle));
        Assert.That(imageData.Structure.RowLengthFieldSize, Is.EqualTo(sizeof(ushort)));
        Assert.That(imageData.Structure.RowByteCounts, Has.Length.EqualTo(3));
        Assert.That(imageData.Structure.RowByteCounts[0], Is.EqualTo(2U));
        Assert.That(imageData.Structure.RowByteCounts[1], Is.EqualTo(0xABCDU));
        Assert.That(imageData.Structure.RowByteCounts[2], Is.EqualTo(1U));
        Assert.That(imageData.Structure.CompressedPayloadLength, Is.EqualTo(1));
    }