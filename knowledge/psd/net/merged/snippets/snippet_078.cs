protected static void AssertByteExactRoundTrip(string fileName)
    {
        string testFile = GetTestDataPath(fileName);
        string outputFile = GetPersistentArtifactPath(fileName);
        byte[] originalBytes = File.ReadAllBytes(testFile);

        using var image = PsdImage.Load(testFile);
        image.Save(outputFile);
        LogArtifactDirectory(outputFile);

        byte[] savedBytes = File.ReadAllBytes(outputFile);
        Assert.That(savedBytes, Is.EqualTo(originalBytes));
    }