[Fact]
    public void SavingAfterDisposeDoesNotOverwriteAnExistingDeck()
    {
        var path = _workspace.PathFor("existing-deck.pptx");

        using (var original = new Presentation())
        {
            original.Slides.AddEmptySlide(original.LayoutSlides[0]);
            original.Save(path, SaveFormat.Pptx);
        }

        var lengthBefore = new FileInfo(path).Length;

        var presentation = new Presentation();
        presentation.Dispose();
        Record.Exception(() => presentation.Save(path, SaveFormat.Pptx));

        var lengthAfter = new FileInfo(path).Length;

        Assert.True(lengthBefore == lengthAfter,
            $"A save that could not succeed truncated an existing deck from {lengthBefore} to {lengthAfter} bytes.");
    }