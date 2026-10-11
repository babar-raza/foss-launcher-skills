[Fact]
    public void Gif_ReportsFormatAndDimensions()
    {
        var info = ImageProbe.Probe(SampleImages.Gif(320, 240));

        Assert.Equal(ImageFormat.Gif, info.Format);
        Assert.Equal(320, info.Width);
        Assert.Equal(240, info.Height);
        Assert.Equal(1, info.FrameCount);
    }