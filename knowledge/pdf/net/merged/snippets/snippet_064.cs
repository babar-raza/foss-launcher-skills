[Fact]
    public void MarkedContent_BDC_WithProperties_FiresEvent()
    {
        var parser = CreateParser();
        string? capturedTag = null;
        PdfDictionary? capturedProps = null;

        parser.OnMarkedContentBegin += (tag, props) =>
        {
            capturedTag = tag;
            capturedProps = props;
        };

        var content = Encoding.ASCII.GetBytes("/Span << /MCID 0 >> BDC\nEMC");
        parser.Parse(content);

        Assert.Equal("Span", capturedTag);
        Assert.NotNull(capturedProps);
        Assert.Equal(0, capturedProps!.GetInt("MCID"));
    }