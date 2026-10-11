[Fact]
    public void CreateUri_ProducesValidActionDict()
    {
        var action = PdfAction.CreateUri("https://example.com");

        Assert.Equal(ActionType.URI, action.Type);
    }