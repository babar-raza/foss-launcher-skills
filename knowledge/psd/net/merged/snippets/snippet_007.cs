[Test]
    public void Resources_OfficialShape_Reads()
    {
        using var image = (PsdImage)Image.Load(GetTestDataPath("test.psd"));

        ResourceBlock[] imageResources = image.ImageResources;
        LayerResource[] globalLayerResources = image.GlobalLayerResources;
        GlobalLayerMaskInfo globalLayerMaskInfo = image.GlobalLayerMaskInfo;
        Layer? activeLayer = image.ActiveLayer;

        Assert.That(image.Size, Is.EqualTo(new Size(image.Width, image.Height)));
        Assert.That(imageResources, Is.Not.Empty);
        Assert.That(imageResources[0].ID, Is.Not.EqualTo(0));
        Assert.That(imageResources[0].DataSize, Is.GreaterThanOrEqualTo(0));
        Assert.That(globalLayerResources, Is.Empty);
        Assert.That(globalLayerMaskInfo, Is.Not.Null);
        Assert.That(activeLayer, Is.SameAs(image.Layers[0]));
        Assert.That(image.IsFlatten, Is.False);
        Assert.That(image.HasTransparencyData, Is.False);
        Assert.That(() => image.ImageResources = imageResources, Throws.TypeOf<NotSupportedException>());
        Assert.That(() => image.GlobalLayerResources = globalLayerResources, Throws.TypeOf<NotSupportedException>());
        Assert.That(() => image.ActiveLayer = activeLayer, Throws.TypeOf<NotSupportedException>());
        Assert.That(() => image.HasTransparencyData = true, Throws.TypeOf<NotSupportedException>());
    }