[Fact]
    public void ANotesSlideIsDeclaredAsANotesSlide()
    {
        var path = _workspace.PathFor("speaker-notes.pptx");

        using (var presentation = new Presentation())
        {
            var notes = presentation.Slides[0].NotesSlideManager.AddNotesSlide();
            notes.NotesTextFrame!.Text = "Speaker notes";
            presentation.Save(path, SaveFormat.Pptx);
        }

        using var package = PptxPackage.Open(path);
        PackageAssert.EveryPartHasItsRequiredContentType(package);
    }