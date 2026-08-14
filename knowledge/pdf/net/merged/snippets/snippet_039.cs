[Fact]
    public void IsSorted_Default_False()
    {
        var data = PdfBuilder.BuildWithChoiceField(["C", "A", "B"]);
        using var doc = Document.Open(data);
        var field = (ChoiceField)doc.Form!.Fields[0];
        Assert.False(field.IsSorted);
    }