internal static string? ResolveInputPath(string[] args)
    {
        if (args.Length > 0 && File.Exists(args[0]))
        {
            return Path.GetFullPath(args[0]);
        }

        string repositoryFixture = Path.GetFullPath(
            Path.Combine(AppContext.BaseDirectory, "../../../../../src/Aspose.PSD.FOSS.Test/testdata/test.psd"));

        return File.Exists(repositoryFixture) ? repositoryFixture : null;
    }