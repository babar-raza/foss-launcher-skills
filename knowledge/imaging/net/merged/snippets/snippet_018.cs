[Fact]
    public void Dicom_WithoutDataSet_ReportsFormatOnly()
    {
        var info = ImageProbe.Probe(SampleImages.Dicom());

        Assert.Equal(ImageFormat.Dicom, info.Format);
        Assert.Null(info.Width);
        Assert.Null(info.Height);
    }