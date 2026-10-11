[Test]
    public void Save_ChangesBounds()
    {
        string testFile = Path.Combine(TestContext.CurrentContext.TestDirectory, "testdata", "test.psd");
        string outputFile = GetPersistentArtifactPath("layer_bounds_test.psd");

        using var image = PsdImage.Load(testFile);
        Rectangle newBounds = Rectangle.FromLeftTopRightBottom(10, 20, 40, 60);
        image.Layers[0].Left = newBounds.Left;
        image.Layers[0].Top = newBounds.Top;
        image.Layers[0].Right = newBounds.Right;
        image.Layers[0].Bottom = newBounds.Bottom;
        image.Save(outputFile);
        LogArtifactDirectory(outputFile);

        using var reloaded = PsdImage.Load(outputFile);
        Assert.That(reloaded.Layers[0].Bounds, Is.EqualTo(new Rectangle(0, 0, newBounds.Width, newBounds.Height)));
        Assert.That(reloaded.Layers[0].Left, Is.EqualTo(newBounds.Left));
        Assert.That(reloaded.Layers[0].Top, Is.EqualTo(newBounds.Top));
        Assert.That(reloaded.Layers[0].Right, Is.EqualTo(newBounds.Right));
        Assert.That(reloaded.Layers[0].Bottom, Is.EqualTo(newBounds.Bottom));
    }