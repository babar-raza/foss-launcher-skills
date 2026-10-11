[Test]
    public void ImageLoad_Official_ReturnsPsd()
    {
        using Image image = Image.Load(GetTestDataPath("test.psd"));
        var psdImage = (PsdImage)image;

        Assert.That(psdImage.Width, Is.EqualTo(100));
        Assert.That(psdImage.ChannelsCount, Is.EqualTo(3));
        Assert.That(psdImage.Layers, Has.Length.EqualTo(2));
    }