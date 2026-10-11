protected static void LogArtifactDirectory(string outputFile)
    {
        string outputDirectory = Path.GetDirectoryName(outputFile) ?? string.Empty;
        TestContext.Out.WriteLine($"Saved test artifact directory: {outputDirectory}");
    }