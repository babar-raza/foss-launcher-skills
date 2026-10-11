[Fact]
    public void ColorSpace_SCN_SetsStrokeColorCMYK()
    {
        var parser = CreateParser();
        // CMYK: pure cyan. Four-component SCN converts through the ICC-based
        // CmykToRgbLut (not the spec's algebraic formula), so expect exactly
        // what the LUT gives for (1, 0, 0, 0).
        var content = Encoding.ASCII.GetBytes("1 0 0 0 SCN");
        parser.Parse(content);

        var (r, g, b) = Aspose.Pdf.Devices.CmykToRgbLut.Convert(1, 0, 0, 0);
        Assert.Equal(r / 255.0, parser.State.StrokeR, 3);
        Assert.Equal(g / 255.0, parser.State.StrokeG, 3);
        Assert.Equal(b / 255.0, parser.State.StrokeB, 3);
    }