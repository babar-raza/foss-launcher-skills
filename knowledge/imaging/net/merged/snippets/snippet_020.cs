[Fact]
    public void Dicom_TruncatedDataSet_DegradesGracefullyInsteadOfThrowing()
    {
        var full = SampleImages.DicomWithPixelInfo(rows: 512, columns: 256, bitsAllocated: 16);
        var truncated = full[..^3];

        var info = ImageProbe.Probe(truncated);

        Assert.Equal(ImageFormat.Dicom, info.Format);
    }