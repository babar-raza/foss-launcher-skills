[Fact]
    public void TestMultipleAuthors()
    {
        // Multiple authors can coexist.
        using var pres = new Presentation();
        pres.CommentAuthors.AddAuthor("Alice", "A");
        pres.CommentAuthors.AddAuthor("Bob", "B");
        pres.CommentAuthors.Count.Should().Be(2);
    }