[Fact]
    public void TestRemoveComment()
    {
        // Removing a comment persists.
        using var pres = new Presentation();
        var author = pres.CommentAuthors.AddAuthor("Alice", "A");
        var slide = pres.Slides[0];
        var now = DateTime.Now;
        author.Comments.AddComment("C1", slide, new PointF(1, 1), now);
        author.Comments.AddComment("C2", slide, new PointF(2, 2), now);
        author.Comments.AddComment("C3", slide, new PointF(3, 3), now);
        author.Comments.Count.Should().Be(3);

        author.Comments.RemoveAt(1);
        author.Comments.Count.Should().Be(2);

        using var pres2 = TestHelpers.SaveAndReopen(pres, _tempDir);
        pres2.CommentAuthors[0].Comments.Count.Should().Be(2);
    }