private static string PathTo(string fileName)
    {
        var path = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "test_data", fileName);
        Assert.True(File.Exists(path), $"The fixture '{fileName}' was not copied to '{path}'.");
        return path;
    }