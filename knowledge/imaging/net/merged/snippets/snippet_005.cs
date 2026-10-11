[Fact]
    public void Gif_MultiFrame_ReportsFrameCount()
    {
        var info = ImageProbe.Probe(SampleImages.GifWithFrames(64, 48, frameCount: 5));

        Assert.Equal(ImageFormat.Gif, info.Format);
        Assert.Equal(64, info.Width);
        Assert.Equal(48, info.Height);
        Assert.Equal(5, info.FrameCount);
    }