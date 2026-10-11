[Fact]
    public void ColorSpace_SavedAndRestored()
    {
        var parser = CreateParser();
        var content = Encoding.ASCII.GetBytes("/DeviceRGB cs /DeviceCMYK CS q /CalGray cs /CalRGB CS Q");
        parser.Parse(content);

        Assert.Equal("DeviceRGB", parser.State.FillColorSpace);
        Assert.Equal("DeviceCMYK", parser.State.StrokeColorSpace);
    }