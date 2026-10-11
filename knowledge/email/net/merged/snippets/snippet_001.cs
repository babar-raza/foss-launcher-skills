[Fact]
    public void DirectoryEntryNameOrderingMatchesSpecRules()
    {
        Assert.True(DirectoryEntryNameComparer.Compare("B", "AA") < 0);
        Assert.Equal(0, DirectoryEntryNameComparer.Compare("ab", "AB"));
        Assert.True(DirectoryEntryNameComparer.Compare("ab", "AC") < 0);
    }