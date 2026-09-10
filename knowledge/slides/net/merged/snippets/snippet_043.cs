private string WriteDeckWithNotes(string fileName)
    {
        var path = _workspace.PathFor(fileName);

        using var presentation = new Presentation();
        var notes = presentation.Slides[0].NotesSlideManager.AddNotesSlide();
        notes.NotesTextFrame!.Text = "Speaker notes";
        presentation.Save(path, SaveFormat.Pptx);

        return path;
    }