protected static string GetPersistentArtifactPath(string fileName)
    {
        string testName = SanitizePathSegment(TestContext.CurrentContext.Test.Name);
        string artifactDirectory = Path.Combine(
            TestContext.CurrentContext.WorkDirectory,
            "artifacts",
            nameof(PsdTestFixtureBase),
            testName);

        Directory.CreateDirectory(artifactDirectory);
        return Path.Combine(artifactDirectory, fileName);
    }