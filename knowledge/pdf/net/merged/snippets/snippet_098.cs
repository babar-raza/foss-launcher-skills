[Fact]
    public void SvgDevice_WithOpacity_IncludesFillOpacity()
    {
        var pdf = BuildPdfWithExtGStateContent("GS1", "<< /Type /ExtGState /ca 0.5 >>",
            "/GS1 gs BT /F1 12 Tf 100 700 Td (Hello) Tj ET");
        using var doc = Document.Open(pdf);
        var page = doc.Pages[1];

        var device = new Aspose.Pdf.Devices.SvgDevice();
        var svg = device.Process(page);

        Assert.Contains("fill-opacity=\"0.5\"", svg);
    }