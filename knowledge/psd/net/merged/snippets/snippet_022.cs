[Test]
    public void Load_LayeredPsb_ReadsLayers()
    {
        using var image = PsdImage.Load(GetTestDataPath("layered.psb"));

        Assert.That(image.Version, Is.EqualTo(6));
        Assert.That(image.Header.Version, Is.EqualTo(PsdHeader.PsbVersion));
        Assert.That(image.LayerCount, Is.EqualTo(3));
        Assert.That(image.Layers[0].Name, Is.EqualTo("Background"));
        Assert.That(image.Layers[1].Name, Is.EqualTo("Rectangle 1"));
        Assert.That(image.Layers[2].Name, Is.EqualTo("Ellipse 1"));
        Assert.That(image.Layers[2].Opacity, Is.EqualTo(191));
    }