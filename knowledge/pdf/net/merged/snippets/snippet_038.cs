[Fact]
    public void IsCombo_False_ListBox()
    {
        var data = PdfBuilder.BuildWithChoiceField(["A", "B"], isCombo: false);
        using var doc = Document.Open(data);
        var field = (ChoiceField)doc.Form!.Fields[0];
        Assert.False(field.IsCombo);
    }