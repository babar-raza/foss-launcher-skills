[Test]
    public void Load_TooLongLayerExtra_Throws()
    {
        byte[] layerBytes = BuildLayerRecordBytesWithExtraData([
            0x00, 0x00, 0x00, 0x10,
            0x00, 0x00, 0x00, 0x00
        ]);
        using var stream = new MemoryStream(layerBytes);
        using var reader = new BigEndianReader(stream, leaveOpen: true);

        Assert.That(() => Layer.Load(reader, isLargeDocument: false), Throws.InstanceOf<PsdLoadException>());
    }