[Fact]
    public void TestInsertComment()
    {
        // insert_comment places at the correct index.
        using var pres = new Presentation();
        var author = pres.CommentAuthors.AddAuthor("Alice", "A");
        var slide = pres.Slides[0];
        var now = DateTime.Now;
        author.Comments.AddComment("First", slide, new PointF(1, 1), now);
        author.Comments.AddComment("Third", slide, new PointF(1, 3), now);
        author.Comments.InsertComment(1, "Second", slide, new PointF(1, 2), now);
        author.Comments.Count.Should().Be(3);
        author.Comments[1].Text.Should().Be("Second");
    }