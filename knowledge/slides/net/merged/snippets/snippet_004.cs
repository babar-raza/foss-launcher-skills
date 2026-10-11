private string WriteDeckWithAReply(string fileName)
    {
        var path = _workspace.PathFor(fileName);

        using var presentation = new Presentation();
        var author = presentation.CommentAuthors.AddAuthor("Reviewer", "RV");
        var parent = author.Comments.AddComment("Please check this", presentation.Slides[0], new PointF(10, 10), new DateTime(2024, 1, 1, 9, 0, 0, DateTimeKind.Utc));
        var reply = author.Comments.AddComment("Checked", presentation.Slides[0], new PointF(20, 20), new DateTime(2024, 1, 1, 10, 0, 0, DateTimeKind.Utc));
        reply.ParentComment = parent;
        presentation.Save(path, SaveFormat.Pptx);

        return path;
    }