[Fact]
    public void IsCombo_True()
    {
        var data = PdfBuilder.BuildWithChoiceField(["A", "B"], isCombo: true);
        using var doc = Document.Open(data);
        var field = (ChoiceField)doc.Form!.Fields[0];
        Assert.True(field.IsCombo);
    }