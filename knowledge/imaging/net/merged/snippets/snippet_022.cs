[Fact]
    public void UnknownData_ReportsUnknownFormat()
    {
        var info = ImageProbe.Probe(new byte[] { 1, 2, 3, 4, 5, 6, 7, 8 });

        Assert.Equal(ImageFormat.Unknown, info.Format);
        Assert.Null(info.Width);
        Assert.Null(info.Height);
    }