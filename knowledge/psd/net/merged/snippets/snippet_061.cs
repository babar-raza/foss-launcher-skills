[Test]
    public void Load_NonSeekableStream_Succeeds()
    {
        byte[] bytes = File.ReadAllBytes(Path.Combine(TestContext.CurrentContext.TestDirectory, "testdata", "test.psd"));
        using var stream = new NonSeekableReadStream(bytes);
        using var image = PsdImage.Load(stream);

        Assert.That(image.Width, Is.GreaterThan(0));
        Assert.That(image.Layers.Length, Is.GreaterThan(0));
    }