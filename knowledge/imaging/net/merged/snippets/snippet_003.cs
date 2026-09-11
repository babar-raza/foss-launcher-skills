[Fact]
    public void Jpeg_TruncatedStream_DegradesToFormatOnlyInsteadOfThrowing()
    {
        var info = ImageProbe.Probe(SampleImages.TruncatedJpeg());

        Assert.Equal(ImageFormat.Jpeg, info.Format);
        Assert.Null(info.Width);
        Assert.Null(info.Height);
    }