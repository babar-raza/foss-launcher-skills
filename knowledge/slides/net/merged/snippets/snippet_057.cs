[Fact]
    public void Test_notes_parent_slide()
    {
        // Notes slide references its parent slide.
        using var pres = new Presentation();
        var slide = pres.Slides[0];
        var notes = slide.NotesSlideManager.AddNotesSlide();
        notes.ParentSlide.Should().BeSameAs(slide);
    }