[Test]
    public void Save_LayeredPsb_ChangesBlendMode()
    {
        string testFile = GetTestDataPath("layered.psb");
        string outputFile = GetPersistentArtifactPath("layered_psb_blend_mode_test.psb");

        using var image = PsdImage.Load(testFile);
        image.Layers[1].BlendModeKey = BlendMode.Multiply;
        image.Save(outputFile);
        LogArtifactDirectory(outputFile);

        using var reloaded = PsdImage.Load(outputFile);
        Assert.That(reloaded.Layers[1].BlendModeKey, Is.EqualTo(BlendMode.Multiply));
    }