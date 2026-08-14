[Fact]
    public void Test_notes_header_footer()
    {
        // Header/footer visibility persists.
        using var pres = new Presentation();
        var notes = pres.Slides[0].NotesSlideManager.AddNotesSlide();
        notes.NotesTextFrame.Text = "Notes";
        var hfm = notes.HeaderFooterManager;
        hfm.SetFooterVisibility(true);
        hfm.SetFooterText("Confidential");
        hfm.SetSlideNumberVisibility(true);

        hfm.IsFooterVisible.Should().BeTrue();
        hfm.IsSlideNumberVisible.Should().BeTrue();

        using var pres2 = TestHelpers.SaveAndReopen(pres, _tempDir);
        var ns2 = pres2.Slides[0].NotesSlideManager.NotesSlide;
        var hfm2 = ns2!.HeaderFooterManager;
        hfm2.IsFooterVisible.Should().BeTrue();
        hfm2.IsSlideNumberVisible.Should().BeTrue();
    }