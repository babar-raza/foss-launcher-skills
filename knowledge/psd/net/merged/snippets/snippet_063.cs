[Test]
    public void Load_MissingFile_Throws()
    {
        string missingFile = Path.Combine(_testDir, "missing.psd");
        Assert.That(() => PsdImage.Load(missingFile), Throws.InstanceOf<FileNotFoundException>());
    }