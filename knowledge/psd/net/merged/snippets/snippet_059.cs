[Test]
    public void Load_Layers_Indexable()
    {
        string testFile = Path.Combine(TestContext.CurrentContext.TestDirectory, "testdata", "test.psd");

        using var image = PsdImage.Load(testFile);

        Assert.That(image.Layers[0], Is.Not.Null);
        Assert.That(image.Layers[1], Is.Not.Null);
    }