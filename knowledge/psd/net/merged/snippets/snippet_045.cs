[Test]
    public void Load_LayerInspection_ReadsValues()
    {
        using var image = PsdImage.Load(Path.Combine(TestContext.CurrentContext.TestDirectory, "testdata", "test.psd"));
        Layer firstLayer = image.Layers[0];

        Assert.That(firstLayer.Bounds, Is.EqualTo(new Rectangle(0, 0, 100, 100)));
        Assert.That(firstLayer.Width, Is.EqualTo(firstLayer.Bounds.Width));
        Assert.That(firstLayer.Height, Is.EqualTo(firstLayer.Bounds.Height));
        Assert.That(firstLayer.Top, Is.EqualTo(0));
        Assert.That(firstLayer.Left, Is.EqualTo(0));
        Assert.That(firstLayer.Bottom, Is.EqualTo(100));
        Assert.That(firstLayer.Right, Is.EqualTo(100));
        Assert.That(firstLayer.ChannelsCount, Is.GreaterThan(0));
        Assert.That(firstLayer.RawBlendModeKey, Has.Length.EqualTo(4));
        Assert.That(firstLayer.LayerMaskData, Is.Null);
        Assert.That(firstLayer.LayerBlendingRangesData.Length, Is.EqualTo(firstLayer.BlendingRangesInfo.RawDataLength - sizeof(uint)));
        Assert.That(firstLayer.AdditionalLayerData, Is.Not.Empty);
    }