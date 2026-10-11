[Test]
    public void Load_TruncatedRleRows_Throws()
    {
        using var stream = new MemoryStream(BuildImageDataSection(CompressionMethod.RLE, [0x00, 0x02, 0xAB, 0xCD, 0x00]));
        using var reader = new BigEndianReader(stream, leaveOpen: true);

        Assert.That(() => ImageData.Load(reader, isLargeDocument: false, height: 1, channelCount: 3), Throws.InstanceOf<PsdLoadException>());
    }