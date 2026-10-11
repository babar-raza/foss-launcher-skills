[Fact]
    public void ANotesMasterIsRegisteredInThePresentationPart()
    {
        var path = WriteDeckWithNotes("notes-master-idlst.pptx");

        using var package = PptxPackage.Open(path);

        var registered = PackageAssert.Select(
            package, "ppt/presentation.xml", "//p:notesMasterIdLst/p:notesMasterId");

        Assert.True(registered.Count == 1,
            $"ppt/presentation.xml registers {registered.Count} notes master(s), expected exactly one." +
            $"{Environment.NewLine}{PackageAssert.Describe(package, "ppt/presentation.xml")}");
    }