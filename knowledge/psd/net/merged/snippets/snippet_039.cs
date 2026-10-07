[Test]
    public void Save_ResourcesFixture_Raw()
    {
        string testFile = GetTestDataPath("resources.psd");
        byte[] originalBytes = File.ReadAllBytes(testFile);
        string outputFile = GetPersistentArtifactPath("resources_fixture_roundtrip_test.psd");

        using var image = PsdImage.Load(testFile);
        image.Save(outputFile);
        LogArtifactDirectory(outputFile);

        byte[] savedBytes = File.ReadAllBytes(outputFile);
        Assert.That(ExtractImageResourcesSection(savedBytes), Is.EqualTo(ExtractImageResourcesSection(originalBytes)));
    }