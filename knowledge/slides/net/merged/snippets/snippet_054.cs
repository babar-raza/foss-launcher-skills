[Fact]
    public void Test_add_notes()
    {
        // Notes text persists after save/reload.
        using var pres = new Presentation();
        var slide = pres.Slides[0];
        var notes = slide.NotesSlideManager.AddNotesSlide();
        notes.NotesTextFrame.Text = "Speaker notes";

        using var pres2 = TestHelpers.SaveAndReopen(pres, _tempDir);
        var ns2 = pres2.Slides[0].NotesSlideManager.NotesSlide;
        ns2.Should().NotBeNull();
        ns2!.NotesTextFrame.Text.Should().Be("Speaker notes");
    }