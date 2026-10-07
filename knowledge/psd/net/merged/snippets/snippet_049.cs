[Test]
    public void Save_ChangesCoordinates()
    {
        string testFile = Path.Combine(TestContext.CurrentContext.TestDirectory, "testdata", "test.psd");
        string outputFile = GetPersistentArtifactPath("layer_coordinates_test.psd");

        using var image = PsdImage.Load(testFile);
        Layer layer = image.Layers[0];
        layer.Top = 10;
        layer.Left = 20;
        layer.Bottom = 30;
        layer.Right = 50;
        image.Save(outputFile);
        LogArtifactDirectory(outputFile);

        using var reloaded = PsdImage.Load(outputFile);
        Assert.That(reloaded.Layers[0].Bounds, Is.EqualTo(new Rectangle(0, 0, 30, 20)));
        Assert.That(reloaded.Layers[0].Left, Is.EqualTo(20));
        Assert.That(reloaded.Layers[0].Top, Is.EqualTo(10));
        Assert.That(reloaded.Layers[0].Right, Is.EqualTo(50));
        Assert.That(reloaded.Layers[0].Bottom, Is.EqualTo(30));
    }