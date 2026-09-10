[Fact]
    public void TestAddAuthor()
    {
        // Author name and initials persist.
        using var pres = new Presentation();
        var author = pres.CommentAuthors.AddAuthor("Alice", "A");
        author.Name.Should().Be("Alice");
        author.Initials.Should().Be("A");
        pres.CommentAuthors.Count.Should().Be(1);

        using var pres2 = TestHelpers.SaveAndReopen(pres, _tempDir);
        pres2.CommentAuthors.Count.Should().Be(1);
        pres2.CommentAuthors[0].Name.Should().Be("Alice");
        pres2.CommentAuthors[0].Initials.Should().Be("A");
    }