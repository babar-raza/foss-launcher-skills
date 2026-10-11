[Fact]
    public void Ico_ReportsFormatDimensionsAndFrameCount()
    {
        var info = ImageProbe.Probe(SampleImages.Ico(32, 32, 32, imageCount: 3));

        Assert.Equal(ImageFormat.Ico, info.Format);
        Assert.Equal(32, info.Width);
        Assert.Equal(32, info.Height);
        Assert.Equal(3, info.FrameCount);
    }