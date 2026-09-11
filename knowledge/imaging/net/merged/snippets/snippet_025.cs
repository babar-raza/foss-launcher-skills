[Fact]
    public void Probe_NonSeekableStream_StillWorks()
    {
        var info = ImageProbe.Probe(new NonSeekableStream(SampleImages.Png(30, 20)));

        Assert.Equal(ImageFormat.Png, info.Format);
        Assert.Equal(30, info.Width);
        Assert.Equal(20, info.Height);
    }