[Fact]
    public void Options_ParsesStringOptions()
    {
        var data = PdfBuilder.BuildWithChoiceField(["Red", "Green", "Blue"]);
        using var doc = Document.Open(data);
        var field = (ChoiceField)doc.Form!.Fields[0];

        var options = field.Options;
        Assert.Equal(3, options.Count);
        Assert.Equal("Red", options[1].ExportValue);
        Assert.Equal("Red", options[1].DisplayValue);
        Assert.Equal("Green", options[2].ExportValue);
        Assert.Equal("Blue", options[3].ExportValue);
    }