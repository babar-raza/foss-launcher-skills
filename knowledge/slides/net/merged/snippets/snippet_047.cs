[Fact]
    public void AConnectorWritesTheConnectionSitesItWasGiven()
    {
        var path = _workspace.PathFor("connector.pptx");

        using (var presentation = new Presentation())
        {
            var shapes = presentation.Slides[0].Shapes!;
            var start = shapes.AddAutoShape(ShapeType.Rectangle, 10, 10, 100, 50);
            var end = shapes.AddAutoShape(ShapeType.Rectangle, 200, 10, 100, 50);
            var connector = shapes.AddConnector(ShapeType.BentConnector3, 0, 0, 1, 1);
            connector.StartShapeConnectedTo = start;
            connector.StartShapeConnectionSiteIndex = 3;
            connector.EndShapeConnectedTo = end;
            connector.EndShapeConnectionSiteIndex = 1;
            presentation.Save(path, SaveFormat.Pptx);
        }

        using var package = PptxPackage.Open(path);

        PackageAssert.ElementWithAttributes(package, "ppt/slides/slide1.xml", "//p:cxnSp/p:nvCxnSpPr/p:cNvCxnSpPr/a:stCxn", ("idx", "3"));
        PackageAssert.ElementWithAttributes(package, "ppt/slides/slide1.xml", "//p:cxnSp/p:nvCxnSpPr/p:cNvCxnSpPr/a:endCxn", ("idx", "1"));
    }