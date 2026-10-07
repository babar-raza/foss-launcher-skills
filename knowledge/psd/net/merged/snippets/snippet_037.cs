[Test]
    public void Save_Resources_PreservesRaw()
    {
        string testFile = Path.Combine(TestContext.CurrentContext.TestDirectory, "testdata", "test.psd");
        byte[] originalBytes = File.ReadAllBytes(testFile);
        string outputFile = GetPersistentArtifactPath("resources_roundtrip_test.psd");

        using var image = PsdImage.Load(testFile);
        image.Save(outputFile);
        LogArtifactDirectory(outputFile);

        byte[] savedBytes = File.ReadAllBytes(outputFile);
        byte[] originalResourcesSection = ExtractImageResourcesSection(originalBytes);
        byte[] savedResourcesSection = ExtractImageResourcesSection(savedBytes);

        Assert.That(savedResourcesSection, Is.EqualTo(originalResourcesSection));

        using var reloaded = PsdImage.Load(outputFile);
        Assert.That(reloaded.HasImageResources, Is.True);
        Assert.That(reloaded.ResourceCount, Is.EqualTo(26));
    }