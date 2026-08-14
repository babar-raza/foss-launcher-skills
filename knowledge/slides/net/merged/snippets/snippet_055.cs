[Fact]
    public void Test_remove_notes()
    {
        // Removing notes persists.
        using var pres = new Presentation();
        var mgr = pres.Slides[0].NotesSlideManager;
        mgr.AddNotesSlide();
        mgr.NotesSlide.Should().NotBeNull();

        mgr.RemoveNotesSlide();
        mgr.NotesSlide.Should().BeNull();

        using var pres2 = TestHelpers.SaveAndReopen(pres, _tempDir);
        pres2.Slides[0].NotesSlideManager.NotesSlide.Should().BeNull();
    }