[Fact]
    public void Gif_TruncatedAfterScreenDescriptor_ReportsDimensionsButNoFrameCount()
    {
        var info = ImageProbe.Probe(SampleImages.GifWithoutFrames(64, 48));

        Assert.Equal(ImageFormat.Gif, info.Format);
        Assert.Equal(64, info.Width);
        Assert.Equal(48, info.Height);
        Assert.Null(info.FrameCount);
    }