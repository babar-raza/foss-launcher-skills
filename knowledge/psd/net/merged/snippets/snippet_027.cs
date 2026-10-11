[Test]
    public void Save_LayerVariants_PreservesTail()
    {
        string testFile = GetTestDataPath("layer-variants.psd");
        byte[] originalBytes = File.ReadAllBytes(testFile);
        string outputFile = GetPersistentArtifactPath("layer_variants_tail_test.psd");

        using var image = PsdImage.Load(testFile);
        image.Layers[2].Name = "Ellipse 1 Updated";
        image.Save(outputFile);
        LogArtifactDirectory(outputFile);

        byte[] savedBytes = File.ReadAllBytes(outputFile);
        Assert.That(ReadLayerAndMaskTail(savedBytes), Is.EqualTo(ReadLayerAndMaskTail(originalBytes)));
    }