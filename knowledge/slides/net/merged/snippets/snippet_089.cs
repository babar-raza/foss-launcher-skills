[Fact]
    public void TestAddComment()
    {
        // Comment text, position, and time persist.
        using var pres = new Presentation();
        var author = pres.CommentAuthors.AddAuthor("Alice", "A");
        var slide = pres.Slides[0];
        var now = new DateTime(2026, 1, 15, 12, 0, 0);
        var comment = author.Comments.AddComment("Review note", slide, new PointF(2.0f, 3.0f), now);
        comment.Text.Should().Be("Review note");
        comment.Author.Name.Should().Be("Alice");

        using var pres2 = TestHelpers.SaveAndReopen(pres, _tempDir);
        var a2 = pres2.CommentAuthors[0];
        a2.Comments.Count.Should().Be(1);
        var c = a2.Comments[0];
        c.Text.Should().Be("Review note");
    }