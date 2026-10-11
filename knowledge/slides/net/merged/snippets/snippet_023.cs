[Fact]
    public void AnEnabledSoftEdgeCarriesItsRadius()
    {
        var path = WriteShapeWithEffect("SoftEdge", "effect-softEdge-rad.pptx");

        using var package = PptxPackage.Open(path);
        var element = PackageAssert.SingleElement(package, "ppt/slides/slide1.xml", "//a:effectLst/a:softEdge");

        Assert.True(element.Attribute("rad") is not null,
            $"<a:softEdge> was written as '{element}'. 'rad' is a required attribute of CT_SoftEdgesEffect.");
    }