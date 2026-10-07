protected static void AssertRenameSave(string fileName, int layerIndex, string newName)
    {
        string testFile = GetTestDataPath(fileName);
        string outputFile = GetPersistentArtifactPath($"renamed_{fileName}");

        using var image = PsdImage.Load(testFile);
        image.Layers[layerIndex].Name = newName;
        image.Save(outputFile);
        LogArtifactDirectory(outputFile);

        using var reloaded = PsdImage.Load(outputFile);
        Assert.That(reloaded.Layers[layerIndex].Name, Is.EqualTo(newName));
    }