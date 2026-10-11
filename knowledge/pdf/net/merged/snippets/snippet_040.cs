[Fact]
    public void SelectedValue_FromField()
    {
        var data = PdfBuilder.BuildWithChoiceField(["Red", "Green", "Blue"], selected: "Blue");
        using var doc = Document.Open(data);
        var field = (ChoiceField)doc.Form!.Fields[0];
        Assert.Equal("Blue", field.Value);
    }