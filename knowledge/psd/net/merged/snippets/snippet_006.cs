[Test]
    public void ImageSetters_UpdateMetadata()
    {
        using var image = (PsdImage)Image.Load(GetTestDataPath("test.psd"));
        Layer[] layers = image.Layers;
        int version = image.Version;

        image.ColorMode = ColorModes.Rgb;
        image.Layers = layers;
        image.GlobalAngle = 45;
        image.Version = version;

        Assert.That(image.ColorMode, Is.EqualTo(ColorModes.Rgb));
        Assert.That(image.Layers, Has.Length.EqualTo(layers.Length));
        Assert.That(image.GlobalAngle, Is.EqualTo(45));
        Assert.That(image.Version, Is.EqualTo(version));
    }