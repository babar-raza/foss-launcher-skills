[Test]
    public void Load_TooLongColorMode_Throws()
    {
        byte[] bytes = File.ReadAllBytes(Path.Combine(TestContext.CurrentContext.TestDirectory, "testdata", "test.psd"));
        WriteUInt32BigEndian(bytes, 26, 100000);
        using var stream = new MemoryStream(bytes);

        Assert.That(() => PsdImage.Load(stream), Throws.InstanceOf<PsdLoadException>());
    }