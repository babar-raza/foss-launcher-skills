[Test]
    public void Load_PsbLayerRecord_Reads()
    {
        using var stream = new MemoryStream(BuildPsbLayerRecordBytes());
        using var reader = new BigEndianReader(stream, leaveOpen: true);

        Layer layer = Layer.Load(reader, isLargeDocument: true);

        Assert.That(layer.Name, Is.EqualTo("Layer 1"));
        Assert.That(layer.Bounds, Is.EqualTo(new Rectangle(0, 0, 1, 1)));
        Assert.That(layer.Opacity, Is.EqualTo(200));
        Assert.That(layer.IsVisible, Is.True);
    }