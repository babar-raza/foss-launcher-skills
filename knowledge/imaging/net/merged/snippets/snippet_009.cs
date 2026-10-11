[Theory]
    [InlineData("lossy")]
    [InlineData("lossless")]
    [InlineData("extended")]
    public void WebP_ReportsFormatAndDimensions(string variant)
    {
        var bytes = variant switch
        {
            "lossy" => SampleImages.WebPLossy(400, 300),
            "lossless" => SampleImages.WebPLossless(400, 300),
            _ => SampleImages.WebPExtended(400, 300),
        };

        var info = ImageProbe.Probe(bytes);

        Assert.Equal(ImageFormat.WebP, info.Format);
        Assert.Equal(400, info.Width);
        Assert.Equal(300, info.Height);
    }