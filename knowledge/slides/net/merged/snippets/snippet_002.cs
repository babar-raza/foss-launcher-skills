[Fact]
    public void ReplyingToACommentWritesNoAttributeTheSchemaDoesNotDeclare()
    {
        var path = WriteDeckWithAReply("comment-reply.pptx");

        using var package = PptxPackage.Open(path);

        var commentParts = package.PartNames
            .Where(name => name.StartsWith("ppt/comments/", StringComparison.Ordinal))
            .ToList();
        Assert.True(commentParts.Count > 0,
            $"No comments part was written. Parts: {string.Join(", ", package.PartNames)}");

        var undeclared = new List<string>();
        foreach (var part in commentParts)
        {
            foreach (var element in package.Xml(part).Descendants())
            {
                foreach (var attribute in element.Attributes().Where(a => a.Name.LocalName == "parentCmId"))
                    undeclared.Add($"{part}: <{element.Name.LocalName} {attribute.Name.LocalName}=\"{attribute.Value}\">");
            }
        }

        Assert.True(undeclared.Count == 0,
            $"The comments part carries {undeclared.Count} 'parentCmId' attribute(s), which CT_Comment does not " +
            $"declare. Threading is expressed by a threadedComments part, not by an attribute on <p:cm>." +
            $"{Environment.NewLine}{string.Join(Environment.NewLine, undeclared)}");
    }