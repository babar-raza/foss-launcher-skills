[Fact]
    public void DetectFormat_MatchesProbeFormat()
    {
        var format = ImageProbe.DetectFormat(SampleImages.Png(10, 10));

        Assert.Equal(ImageFormat.Png, format);
    }