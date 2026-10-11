[Fact]
    public void MultipleFields_ChoiceOptions()
    {
        var data = PdfBuilder.BuildWithMultipleFields();
        using var doc = Document.Open(data);
        var field = doc.Form!.FindByName("color");
        Assert.NotNull(field);
        Assert.IsType<ComboBoxField>(field);

        var choice = (ComboBoxField)field!;
        Assert.Equal(3, choice.Options.Count);
        Assert.Equal("Red", choice.Options[1].ExportValue);
        Assert.Equal("Green", choice.Options[2].ExportValue);
        Assert.Equal("Blue", choice.Options[3].ExportValue);
    }