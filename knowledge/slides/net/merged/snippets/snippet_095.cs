[Fact]
    public void TestRemoveAuthor()
    {
        // Removing an author persists.
        using var pres = new Presentation();
        pres.CommentAuthors.AddAuthor("Alice", "A");
        pres.CommentAuthors.AddAuthor("Bob", "B");
        pres.CommentAuthors.Remove(pres.CommentAuthors[0]);
        pres.CommentAuthors.Count.Should().Be(1);

        using var pres2 = TestHelpers.SaveAndReopen(pres, _tempDir);
        pres2.CommentAuthors.Count.Should().Be(1);
        pres2.CommentAuthors[0].Name.Should().Be("Bob");
    }