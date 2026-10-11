[Test]
    public void Save_LayerVariants_Clipping()
    {
        string testFile = GetTestDataPath("layer-variants.psd");
        string outputFile = GetPersistentArtifactPath("layer_variants_clipping_test.psd");

        using var image = PsdImage.Load(testFile);
        image.Layers[3].Clipping = 0;
        image.Save(outputFile);
        LogArtifactDirectory(outputFile);

        using var reloaded = PsdImage.Load(outputFile);
        Assert.That(reloaded.Layers[3].Clipping, Is.EqualTo(0));
    }