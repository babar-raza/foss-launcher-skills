[Fact]
    public void Wmf_Placeable_ReportsDimensionsAt96Dpi()
    {
        var info = ImageProbe.Probe(SampleImages.Wmf(200, 100));

        Assert.Equal(ImageFormat.Wmf, info.Format);
        Assert.Equal(200, info.Width);
        Assert.Equal(100, info.Height);
    }