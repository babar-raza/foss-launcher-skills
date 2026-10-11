protected static string GetTestDataPath(string fileName)
    {
        string testDirectoryPath = Path.Combine(TestContext.CurrentContext.TestDirectory, "testdata", fileName);
        if (File.Exists(testDirectoryPath))
        {
            return testDirectoryPath;
        }

        string repositoryPath = Path.GetFullPath(Path.Combine(TestContext.CurrentContext.TestDirectory, "../../../testdata", fileName));
        return repositoryPath;
    }