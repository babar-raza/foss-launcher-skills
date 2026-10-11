[Fact]
    public void SavingAPowerPointDeckUnchangedKeepsEveryPart()
    {
        var path = _workspace.PathFor("roundtrip-unchanged.pptx");

        using (var presentation = new Presentation(TestFixtures.PowerPointDeck))
        {
            presentation.Save(path, SaveFormat.Pptx);
        }

        AssertSamePartSet(TestFixtures.PowerPointDeck, path);
    }