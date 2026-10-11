[Test]
    public void Save_OfficialMutation_Persists()
    {
        string outputFile = GetPersistentArtifactPath("official_style_layer_mutation.psd");

        using (var image = (PsdImage)Image.Load(GetTestDataPath("test.psd")))
        {
            image.Layers[0].Name = "Official style";
            image.Layers[0].Left = 10;
            image.Layers[0].Top = 20;
            image.Layers[0].Right = 40;
            image.Layers[0].Bottom = 60;
            image.Layers[0].BlendModeKey = BlendMode.Multiply;
            image.Save(outputFile);
        }

        using var reloaded = (PsdImage)Image.Load(outputFile);
        Assert.That(reloaded.Layers[0].Name, Is.EqualTo("Official style"));
        Assert.That(reloaded.Layers[0].Bounds, Is.EqualTo(new Rectangle(0, 0, 30, 40)));
        Assert.That(reloaded.Layers[0].Left, Is.EqualTo(10));
        Assert.That(reloaded.Layers[0].Top, Is.EqualTo(20));
        Assert.That(reloaded.Layers[0].Right, Is.EqualTo(40));
        Assert.That(reloaded.Layers[0].Bottom, Is.EqualTo(60));
        Assert.That(reloaded.Layers[0].BlendModeKey, Is.EqualTo(BlendMode.Multiply));
    }