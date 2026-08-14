[Fact]
    public void CreateLaunch_StoresFilePath()
    {
        var action = PdfAction.CreateLaunch("/path/to/file.pdf");

        Assert.Equal(ActionType.Launch, action.Type);
    }