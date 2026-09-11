[Fact]
    public void Tiff_LittleEndian_ReportsFormatAndDimensions()
    {
        var info = ImageProbe.Probe(SampleImages.Tiff(1600, 1200, 8));

        Assert.Equal(ImageFormat.Tiff, info.Format);
        Assert.Equal(1600, info.Width);
        Assert.Equal(1200, info.Height);
        Assert.Equal(8, info.BitDepth);
        Assert.Equal(1, info.FrameCount);
    }