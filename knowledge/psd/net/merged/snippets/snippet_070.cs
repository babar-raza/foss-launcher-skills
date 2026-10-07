[Test]
    public void Save_ChangesLayerOpacity()
    {
        string testFile = Path.Combine(TestContext.CurrentContext.TestDirectory, "testdata", "test.psd");
        string outputFile = GetPersistentArtifactPath("layer_opacity_test.psd");

        using var image = PsdImage.Load(testFile);

        Assert.That(image.Layers.Length, Is.GreaterThan(0));

        byte originalOpacity = image.Layers[0].Opacity;
        byte newOpacity = (byte)Math.Max(0, originalOpacity - 50);
        image.Layers[0].Opacity = newOpacity;

        image.Save(outputFile);
        LogArtifactDirectory(outputFile);

        using var reloaded = PsdImage.Load(outputFile);

        Assert.That(reloaded.Layers[0].Opacity, Is.EqualTo(newOpacity));
    }