[Test]
    public void Load_LayerDtos_ReadValues()
    {
        using var image = PsdImage.Load(Path.Combine(TestContext.CurrentContext.TestDirectory, "testdata", "test.psd"));
        Layer layer = image.Layers[0];

        Assert.That(layer.Channels, Has.Count.EqualTo(4));
        Assert.That(layer.Channels[0].ChannelId, Is.EqualTo((short)-1));
        Assert.That(layer.Channels[1].ChannelId, Is.EqualTo((short)0));
        Assert.That(layer.Channels[2].ChannelId, Is.EqualTo((short)1));
        Assert.That(layer.Channels[3].ChannelId, Is.EqualTo((short)2));
        Assert.That(layer.Channels[0].DataLength, Is.GreaterThan(0UL));

        Assert.That(layer.MaskInfo.IsPresent, Is.False);
        Assert.That(layer.MaskInfo.RawDataLength, Is.EqualTo(4));
        Assert.That(layer.BlendingRangesInfo.IsPresent, Is.True);
        Assert.That(layer.BlendingRangesInfo.RawDataLength, Is.EqualTo(44));
    }