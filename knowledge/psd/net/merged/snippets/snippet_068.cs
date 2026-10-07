[Test]
    public void Save_ChangesLayerName()
    {
        string testFile = Path.Combine(TestContext.CurrentContext.TestDirectory, "testdata", "test.psd");
        string outputFile = GetPersistentArtifactPath("layer_name_test.psd");

        using var image = PsdImage.Load(testFile);

        Assert.That(image.Layers.Length, Is.GreaterThan(0));

        string originalName = image.Layers[0].Name;
        image.Layers[0].Name = "Test Layer Name";

        image.Save(outputFile);
        LogArtifactDirectory(outputFile);

        using var reloaded = PsdImage.Load(outputFile);

        Assert.That(reloaded.Layers[0].Name, Is.EqualTo("Test Layer Name"));
    }