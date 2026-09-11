[Fact]
    public void Bmp_ReportsFormatAndDimensions()
    {
        var info = ImageProbe.Probe(SampleImages.Bmp(200, 100, 24));

        Assert.Equal(ImageFormat.Bmp, info.Format);
        Assert.Equal(200, info.Width);
        Assert.Equal(100, info.Height);
        Assert.Equal(24, info.BitDepth);
    }