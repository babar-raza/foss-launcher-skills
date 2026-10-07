[Test]
    public void Channels_OfficialShape_ReadsOnly()
    {
        using var image = (PsdImage)Image.Load(GetTestDataPath("test.psd"));
        Layer layer = image.Layers[0];

        ChannelInformation[] channelInformation = layer.ChannelInformation;

        Assert.That(layer.ChannelsCount, Is.EqualTo(channelInformation.Length));
        Assert.That(channelInformation, Is.Not.Empty);
        Assert.That(channelInformation[0].Length, Is.GreaterThan(0));
        Assert.That(() => layer.ChannelInformation = channelInformation, Throws.TypeOf<NotSupportedException>());
    }