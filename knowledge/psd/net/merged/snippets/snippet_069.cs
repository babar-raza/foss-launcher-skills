[Test]
    public void Save_ChangesLayerVisibility()
    {
        string testFile = Path.Combine(TestContext.CurrentContext.TestDirectory, "testdata", "test.psd");
        string outputFile = GetPersistentArtifactPath("layer_visible_test.psd");

        using var image = PsdImage.Load(testFile);

        Assert.That(image.Layers.Length, Is.GreaterThan(0));

        bool originalVisible = image.Layers[0].IsVisible;
        image.Layers[0].IsVisible = !originalVisible;

        image.Save(outputFile);
        LogArtifactDirectory(outputFile);

        using var reloaded = PsdImage.Load(outputFile);

        Assert.That(reloaded.Layers[0].IsVisible, Is.EqualTo(!originalVisible));
    }