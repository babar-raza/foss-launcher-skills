[Fact]
    public void Ico_ZeroDimensionByte_MeansTwoFiftySixPixels()
    {
        var info = ImageProbe.Probe(SampleImages.Ico(0, 0, 32));

        Assert.Equal(256, info.Width);
        Assert.Equal(256, info.Height);
    }