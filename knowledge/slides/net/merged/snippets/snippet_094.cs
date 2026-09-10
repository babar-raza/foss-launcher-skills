[Fact]
    public void TestClearComments()
    {
        // clear() removes all comments from an author.
        using var pres = new Presentation();
        var author = pres.CommentAuthors.AddAuthor("Alice", "A");
        var slide = pres.Slides[0];
        var now = DateTime.Now;
        author.Comments.AddComment("C1", slide, new PointF(1, 1), now);
        author.Comments.AddComment("C2", slide, new PointF(2, 2), now);
        author.Comments.Clear();
        author.Comments.Count.Should().Be(0);
    }