[Fact]
    public void NoThemePartIsSharedBetweenTwoMasters()
    {
        var path = WriteDeckWithNotes("notes-master-theme.pptx");

        using var package = PptxPackage.Open(path);

        AssertEachMasterHasItsOwnTheme(package);
    }