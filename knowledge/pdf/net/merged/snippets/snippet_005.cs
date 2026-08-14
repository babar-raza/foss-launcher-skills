[Fact]
    public void CreateJavaScript_StoresScript()
    {
        var action = PdfAction.CreateJavaScript("app.alert('Hello');");

        Assert.Equal(ActionType.JavaScript, action.Type);
    }