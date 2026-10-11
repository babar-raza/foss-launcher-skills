[Fact]
    public void ColorSpace_cs_SetsFillColorSpace()
    {
        var parser = CreateParser();
        var content = Encoding.ASCII.GetBytes("/DeviceRGB cs");
        parser.Parse(content);

        Assert.Equal("DeviceRGB", parser.State.FillColorSpace);
    }