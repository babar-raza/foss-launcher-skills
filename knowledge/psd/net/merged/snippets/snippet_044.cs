[Test]
    public void Load_NegativeLayerExtra_Throws()
    {
        byte[] layerBytes = BuildLayerRecordBytesWithExtraData([]);
        WriteUInt32BigEndian(layerBytes, 30, 0xFFFFFFFF);
        using var stream = new MemoryStream(layerBytes);
        using var reader = new BigEndianReader(stream, leaveOpen: true);

        Assert.That(() => Layer.Load(reader, isLargeDocument: false), Throws.InstanceOf<PsdLoadException>());
    }