[Fact]
    public void Png_ReportsFormatAndDimensions()
    {
        var info = ImageProbe.Probe(SampleImages.Png(640, 480, 8));

        Assert.Equal(ImageFormat.Png, info.Format);
        Assert.Equal(640, info.Width);
        Assert.Equal(480, info.Height);
        Assert.Equal(8, info.BitDepth);
        Assert.Equal(1, info.FrameCount);
    }