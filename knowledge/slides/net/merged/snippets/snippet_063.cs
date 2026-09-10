[Theory]
    [MemberData(nameof(FormatsThatCannotBeWritten))]
    public void RequestingAFormatThatCannotBeWrittenRaisesInsteadOfWritingAPowerPointPackage(SaveFormat format)
    {
        var path = _workspace.PathFor($"deck.{format.ToString().ToLowerInvariant()}");

        using var presentation = new Presentation();
        var thrown = Record.Exception(() => presentation.Save(path, format));

        Assert.True(thrown is NotSupportedException,
            $"Save(path, SaveFormat.{format}) {(thrown is null ? "returned successfully" : $"threw {thrown.GetType().Name}")}, " +
            $"expected NotSupportedException. {DescribeWhatWasWritten(path)}");
    }