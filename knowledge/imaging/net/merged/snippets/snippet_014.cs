[Fact]
    public void Tiff_SelfReferencingIfd_DoesNotLoopForever()
    {
        var info = ImageProbe.Probe(SampleImages.TiffWithSelfReferencingIfd(320, 240, 8));

        Assert.Equal(ImageFormat.Tiff, info.Format);
        Assert.Equal(1, info.FrameCount);
    }