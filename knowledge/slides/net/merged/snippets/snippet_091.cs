[Fact]
    public void TestGetSlideComments()
    {
        // get_slide_comments filters by author.
        using var pres = new Presentation();
        var a1 = pres.CommentAuthors.AddAuthor("Alice", "A");
        var a2 = pres.CommentAuthors.AddAuthor("Bob", "B");
        var slide = pres.Slides[0];
        var now = DateTime.Now;
        a1.Comments.AddComment("Alice's", slide, new PointF(1, 1), now);
        a2.Comments.AddComment("Bob's", slide, new PointF(2, 2), now);

        var allC = slide.GetSlideComments(null);
        allC.Count.Should().Be(2);

        var bobC = slide.GetSlideComments(a2);
        bobC.Count.Should().Be(1);
        bobC[0].Text.Should().Be("Bob's");
    }