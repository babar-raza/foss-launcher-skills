[Test]
    public void LayerMask_OfficialShape_Reads()
    {
        using var image = (PsdImage)Image.Load(GetTestDataPath("test.psd"));
        Layer layer = image.Layers[0];

        Assert.That(layer.LayerMaskData, Is.Null);
        Assert.That(layer.LayerBlendingRangesData.Length, Is.EqualTo(40));
        Assert.That(() => layer.LayerMaskData = null, Throws.TypeOf<NotSupportedException>());
        Assert.That(() => layer.LayerBlendingRangesData = new Aspose.PSD.FileFormats.Psd.Layers.LayerBlendingRangesData(), Throws.TypeOf<NotSupportedException>());
    }