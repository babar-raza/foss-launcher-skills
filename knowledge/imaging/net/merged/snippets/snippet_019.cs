[Theory]
    [InlineData(SampleImages.ExplicitVrLittleEndian)]
    [InlineData(SampleImages.ImplicitVrLittleEndian)]
    [InlineData(SampleImages.ExplicitVrBigEndian)]
    public void Dicom_ReportsPixelDimensionsForCommonTransferSyntaxes(string transferSyntax)
    {
        var info = ImageProbe.Probe(SampleImages.DicomWithPixelInfo(rows: 512, columns: 256, bitsAllocated: 16, transferSyntax));

        Assert.Equal(ImageFormat.Dicom, info.Format);
        Assert.Equal(256, info.Width);
        Assert.Equal(512, info.Height);
        Assert.Equal(16, info.BitDepth);
    }