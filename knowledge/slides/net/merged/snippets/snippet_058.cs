[Fact]
    public void Test_notes_size()
    {
        // Notes size has positive width and height.
        using var pres = new Presentation();
        var ns = pres.NotesSize;
        ns.Size.Width.Should().BeGreaterThan(0);
        ns.Size.Height.Should().BeGreaterThan(0);
    }