[Fact]
    public void Bmp_NegativeHeight_ReportsPositiveMagnitude()
    {
        var info = ImageProbe.Probe(SampleImages.Bmp(200, -100, 24));

        Assert.Equal(100, info.Height);
    }