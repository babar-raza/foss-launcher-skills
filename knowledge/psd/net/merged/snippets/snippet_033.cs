[Test]
    public void Load_PsbRle_ReadsStructure()
    {
        using var stream = new MemoryStream(BuildImageDataSection(
            CompressionMethod.RLE,
            [
                0x00, 0x00, 0x00, 0x02,
                0x00, 0x00, 0x00, 0x01,
                0x00, 0x00, 0x00, 0x03,
                0xAB, 0xCD, 0xEF, 0x10, 0x11, 0x12
            ]));
        using var reader = new BigEndianReader(stream, leaveOpen: true);

        ImageData imageData = ImageData.Load(reader, isLargeDocument: true, height: 1, channelCount: 3);

        Assert.That(imageData.Compression, Is.EqualTo(CompressionMethod.RLE));
        Assert.That(imageData.Structure.Kind, Is.EqualTo(ImageDataKind.Rle));
        Assert.That(imageData.Structure.RowLengthFieldSize, Is.EqualTo(sizeof(uint)));
        Assert.That(imageData.Structure.RowByteCounts, Has.Length.EqualTo(3));
        Assert.That(imageData.Structure.RowByteCounts[0], Is.EqualTo(2U));
        Assert.That(imageData.Structure.RowByteCounts[1], Is.EqualTo(1U));
        Assert.That(imageData.Structure.RowByteCounts[2], Is.EqualTo(3U));
        Assert.That(imageData.Structure.CompressedPayloadLength, Is.EqualTo(6));
    }