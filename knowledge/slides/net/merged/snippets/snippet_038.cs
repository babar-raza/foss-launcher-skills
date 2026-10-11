[Fact]
    public void ChangingTheSlideListKeepsThePresentationPartInSchemaOrder()
    {
        var path = _workspace.PathFor("notes-then-slide-change.pptx");

        using (var presentation = new Presentation())
        {
            var notes = presentation.Slides[0].NotesSlideManager.AddNotesSlide();
            notes.NotesTextFrame!.Text = "Speaker notes";
            presentation.Slides.AddEmptySlide(presentation.LayoutSlides[0]);
            presentation.Save(path, SaveFormat.Pptx);
        }

        SchemaValidation.HasNoSchemaErrors(path);
    }