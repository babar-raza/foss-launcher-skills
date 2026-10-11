[Test]
    public void Load_Document_ReadsProperties()
    {
        string testFile = Path.Combine(TestContext.CurrentContext.TestDirectory, "testdata", "test.psd");

        Assert.That(File.Exists(testFile), Is.True, "Test file not found");

        using var image = PsdImage.Load(testFile);

        Assert.That(image.Width, Is.GreaterThan(0));
        Assert.That(image.Height, Is.GreaterThan(0));
        Assert.That(image.Channels, Is.GreaterThan(0));
        Assert.That(image.BitsPerChannel, Is.EqualTo(8));
        Assert.That(image.ColorMode, Is.EqualTo(ColorModes.Rgb));
        Assert.That(image.Version, Is.GreaterThan(0).And.LessThanOrEqualTo(6));
        Assert.That(image.Layers.Length, Is.GreaterThan(0));
    }