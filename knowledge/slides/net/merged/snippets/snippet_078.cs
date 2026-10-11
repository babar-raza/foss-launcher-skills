[Fact]
    public void SettingTheStyleOfATableThatCarriesAnExtensionListKeepsSchemaOrder()
    {
        var path = _workspace.PathFor("table-style-order.pptx");

        using (var presentation = new Presentation(TestFixtures.TableWithExtension))
        {
            var table = (ITable)presentation.Slides[0].Shapes![0];
            table.StylePreset = TableStylePreset.MediumStyle2Accent3;
            presentation.Save(path, SaveFormat.Pptx);
        }

        using var package = PptxPackage.Open(path);

        var properties = PackageAssert.SingleElement(package, "ppt/slides/slide1.xml", "//a:tbl/a:tblPr");
        PackageAssert.ChildrenInSchemaOrder(properties, Ns.A + "tableStyleId", Ns.A + "extLst");

        SchemaValidation.HasNoSchemaErrors(path);
    }