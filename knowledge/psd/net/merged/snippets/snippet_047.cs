[Test]
    public void Save_ChangesClipping()
    {
        string testFile = Path.Combine(TestContext.CurrentContext.TestDirectory, "testdata", "test.psd");
        string outputFile = GetPersistentArtifactPath("layer_clipping_test.psd");
        byte[] originalBytes = File.ReadAllBytes(testFile);

        using var image = PsdImage.Load(testFile);
        image.Layers[0].Clipping = 1;
        image.Save(outputFile);
        LogArtifactDirectory(outputFile);

        using var reloaded = PsdImage.Load(outputFile);
        Assert.That(reloaded.Layers[0].Clipping, Is.EqualTo(1));

        byte[] savedBytes = File.ReadAllBytes(outputFile);
        Assert.That(ReadLayerAndMaskTail(originalBytes), Is.EqualTo(ReadLayerAndMaskTail(savedBytes)));
    }