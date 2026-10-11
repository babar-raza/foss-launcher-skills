[Test]
    public void Save_ChangesBlendMode()
    {
        string testFile = Path.Combine(TestContext.CurrentContext.TestDirectory, "testdata", "test.psd");
        string outputFile = GetPersistentArtifactPath("layer_blend_mode_test.psd");

        using var image = PsdImage.Load(testFile);
        image.Layers[0].BlendModeKey = BlendMode.Multiply;
        image.Save(outputFile);
        LogArtifactDirectory(outputFile);

        using var reloaded = PsdImage.Load(outputFile);
        Assert.That(reloaded.Layers[0].BlendModeKey, Is.EqualTo(BlendMode.Multiply));

        byte[] originalBytes = File.ReadAllBytes(testFile);
        byte[] savedBytes = File.ReadAllBytes(outputFile);
        Assert.That(ReadLayerInfoLength(originalBytes), Is.EqualTo(ReadLayerInfoLength(savedBytes)));
    }