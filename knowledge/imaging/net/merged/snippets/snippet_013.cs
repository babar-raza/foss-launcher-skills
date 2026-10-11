[Fact]
    public void Tiff_MultiPage_ReportsFrameCountFromIfdChain()
    {
        var info = ImageProbe.Probe(SampleImages.TiffWithPages(800, 600, 8, pageCount: 4));

        Assert.Equal(ImageFormat.Tiff, info.Format);
        Assert.Equal(800, info.Width);
        Assert.Equal(600, info.Height);
        Assert.Equal(4, info.FrameCount);
    }