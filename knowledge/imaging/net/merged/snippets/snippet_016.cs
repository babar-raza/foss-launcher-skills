[Fact]
    public void Emf_DerivesDimensionsFromBounds()
    {
        var info = ImageProbe.Probe(SampleImages.Emf(800, 600));

        Assert.Equal(ImageFormat.Emf, info.Format);
        Assert.Equal(800, info.Width);
        Assert.Equal(600, info.Height);
    }