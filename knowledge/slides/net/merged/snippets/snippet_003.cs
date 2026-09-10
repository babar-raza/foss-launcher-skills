[Fact]
    public void ADeckWithACommentReplyProducesASchemaValidPackage()
    {
        var path = WriteDeckWithAReply("comment-reply-valid.pptx");

        SchemaValidation.HasNoSchemaErrors(path);
    }