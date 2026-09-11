[Fact]
    public void Gif_TruncatedMidFrameData_DegradesGracefullyInsteadOfThrowing()
    {
        var full = SampleImages.GifWithFrames(64, 48, frameCount: 3);
        var truncated = full[..^2];

        var info = ImageProbe.Probe(truncated);

        Assert.Equal(ImageFormat.Gif, info.Format);
        Assert.Equal(64, info.Width);
        Assert.Equal(48, info.Height);
    }