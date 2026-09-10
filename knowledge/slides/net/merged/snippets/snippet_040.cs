[Fact]
    public void AddingNotesToAnExistingDeckLeavesEveryMasterItsOwnTheme()
    {
        var path = _workspace.PathFor("loaded-notes.pptx");

        using (var presentation = new Presentation(TestFixtures.SimpleDeck))
        {
            var notes = presentation.Slides[0].NotesSlideManager.AddNotesSlide();
            notes.NotesTextFrame!.Text = "Speaker notes";
            presentation.Save(path, SaveFormat.Pptx);
        }

        using var package = PptxPackage.Open(path);

        AssertEachMasterHasItsOwnTheme(package);
        SchemaValidation.HasNoSchemaErrors(path);
    }