[Fact]
    public void SvgDevice_WithBlendMode_IncludesMixBlendMode()
    {
        var pdf = BuildPdfWithExtGStateContent("GS1", "<< /Type /ExtGState /BM /Multiply >>",
            "/GS1 gs BT /F1 12 Tf 100 700 Td (Hello) Tj ET");
        using var doc = Document.Open(pdf);
        var page = doc.Pages[1];

        var device = new Aspose.Pdf.Devices.SvgDevice();
        var svg = device.Process(page);

        Assert.Contains("mix-blend-mode:multiply", svg);
    }