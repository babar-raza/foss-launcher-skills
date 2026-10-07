[Test]
    public void Metadata_OfficialTypes_Reads()
    {
        using var image = (PsdImage)Image.Load(GetTestDataPath("test.psd"));
        Layer layer = image.Layers[0];

        Rectangle bounds = layer.Bounds;
        BlendMode blendModeKey = layer.BlendModeKey;

        Assert.That(bounds, Is.EqualTo(new Rectangle(0, 0, 100, 100)));
        Assert.That(blendModeKey, Is.EqualTo(BlendMode.Normal));
        Assert.That(layer.Opacity, Is.EqualTo(255));
        Assert.That(layer.IsVisible, Is.True);
    }