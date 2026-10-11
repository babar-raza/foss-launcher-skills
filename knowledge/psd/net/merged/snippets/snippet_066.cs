[Test]
    public void Save_RoundTrip_LoadsAgain()
    {
        string testFile = Path.Combine(TestContext.CurrentContext.TestDirectory, "testdata", "test.psd");
        string outputFile = GetPersistentArtifactPath("roundtrip_test.psd");

        using var image1 = PsdImage.Load(testFile);
        int originalLength = image1.Layers.Length;
        string originalLayerName = image1.Layers.Length > 0 ? image1.Layers[0].Name : string.Empty;
        image1.Save(outputFile);
        LogArtifactDirectory(outputFile);

        using var image2 = PsdImage.Load(outputFile);

        Assert.That(image2.Width, Is.EqualTo(image1.Width));
        Assert.That(image2.Height, Is.EqualTo(image1.Height));
        Assert.That(image2.Channels, Is.EqualTo(image1.Channels));
        Assert.That(image2.BitsPerChannel, Is.EqualTo(image1.BitsPerChannel));
        Assert.That(image2.Layers.Length, Is.EqualTo(originalLength));
        if (image2.Layers.Length > 0)
        {
            Assert.That(image2.Layers[0].Name, Is.EqualTo(originalLayerName));
        }
    }