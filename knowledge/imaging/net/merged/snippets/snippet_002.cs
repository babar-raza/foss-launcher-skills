[Fact]
    public void Jpeg_ReportsFormatAndDimensions()
    {
        var info = ImageProbe.Probe(SampleImages.Jpeg(1024, 768));

        Assert.Equal(ImageFormat.Jpeg, info.Format);
        Assert.Equal(1024, info.Width);
        Assert.Equal(768, info.Height);
        Assert.Equal(8, info.BitDepth);
    }