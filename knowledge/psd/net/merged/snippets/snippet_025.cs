[Test]
    public void Load_LayerVariants_ReadsFlags()
    {
        using var image = PsdImage.Load(GetTestDataPath("layer-variants.psd"));

        Assert.That(image.LayerCount, Is.EqualTo(4));
        Assert.That(image.Layers[1].IsVisible, Is.False);
        Assert.That(image.Layers[2].BlendModeKey, Is.EqualTo(BlendMode.LinearBurn));
        Assert.That(image.Layers[2].RawBlendModeKey, Is.EqualTo("lbrn"));
        Assert.That(image.Layers[3].Clipping, Is.EqualTo(1));
        Assert.That(image.Layers[3].AdditionalLayerData, Is.Not.Empty);
    }