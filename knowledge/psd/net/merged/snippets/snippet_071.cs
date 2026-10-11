[Test]
    public void Save_Mutation_PreservesFlags()
    {
        string testFile = Path.Combine(TestContext.CurrentContext.TestDirectory, "testdata", "test.psd");
        string outputFile = GetPersistentArtifactPath("preserve_flags_and_blend.psd");

        using var image = PsdImage.Load(testFile);
        image.Layers[0].Name = "Renamed";
        image.Save(outputFile);
        LogArtifactDirectory(outputFile);

        using var reloaded = PsdImage.Load(outputFile);
        Assert.That(reloaded.Layers[0].RawBlendModeKey, Is.EqualTo("norm"));
        Assert.That(reloaded.Layers[0].IsVisible, Is.True);
    }