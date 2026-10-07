[Test]
    public void Load_Seekable_PreservesPosition()
    {
        byte[] bytes = File.ReadAllBytes(Path.Combine(TestContext.CurrentContext.TestDirectory, "testdata", "test.psd"));
        byte[] prefix = [1, 2, 3, 4, 5];
        using var stream = new MemoryStream();
        stream.Write(prefix);
        stream.Write(bytes);
        stream.Position = prefix.Length;

        using var image = PsdImage.Load(stream);

        Assert.That(stream.Position, Is.EqualTo(prefix.Length));
        Assert.That(image.Width, Is.GreaterThan(0));
    }