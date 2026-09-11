[Fact]
    public void ProbeFile_ReadsFromDisk()
    {
        var path = Path.GetTempFileName();
        try
        {
            File.WriteAllBytes(path, SampleImages.Png(50, 60));
            var info = ImageProbe.ProbeFile(path);

            Assert.Equal(ImageFormat.Png, info.Format);
            Assert.Equal(50, info.Width);
            Assert.Equal(60, info.Height);
        }
        finally
        {
            File.Delete(path);
        }
    }