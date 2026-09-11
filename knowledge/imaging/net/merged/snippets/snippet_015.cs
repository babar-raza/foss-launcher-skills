[Fact]
    public void Psd_ReportsFormatAndDimensions()
    {
        var info = ImageProbe.Probe(SampleImages.Psd(500, 400, 8));

        Assert.Equal(ImageFormat.Psd, info.Format);
        Assert.Equal(500, info.Width);
        Assert.Equal(400, info.Height);
        Assert.Equal(8, info.BitDepth);
    }