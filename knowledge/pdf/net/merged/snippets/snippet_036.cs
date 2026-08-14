[Fact]
    public void Options_EmptyList()
    {
        var data = PdfBuilder.BuildWithChoiceField([]);
        using var doc = Document.Open(data);
        var field = (ChoiceField)doc.Form!.Fields[0];

        Assert.Empty(field.Options);
    }