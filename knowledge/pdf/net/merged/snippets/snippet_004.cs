[Fact]
    public void CreateGoTo_WithXyzFit_ProducesValidAction()
    {
        var action = PdfAction.CreateGoTo(1, left: 100, top: 500, zoom: 1.5);

        Assert.Equal(ActionType.GoTo, action.Type);
    }