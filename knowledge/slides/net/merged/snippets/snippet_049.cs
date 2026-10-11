[Fact]
    public void EffectsAreWrittenInTheOrderTheEffectListRequires()
    {
        var path = _workspace.PathFor("effect-order.pptx");

        using (var presentation = new Presentation())
        {
            var shape = presentation.Slides[0].Shapes!.AddAutoShape(ShapeType.Rectangle, 10, 10, 100, 100);
            // Enabled in the reverse of schema order on purpose: the writer, not the caller, owns the order.
            shape.EffectFormat!.EnableSoftEdgeEffect();
            shape.EffectFormat.EnableOuterShadowEffect();
            shape.EffectFormat.EnableGlowEffect();
            shape.EffectFormat.EnableBlurEffect();
            presentation.Save(path, SaveFormat.Pptx);
        }

        using var package = PptxPackage.Open(path);
        var effectList = PackageAssert.SingleElement(package, "ppt/slides/slide1.xml", "//a:effectLst");

        PackageAssert.ChildrenInSchemaOrder(
            effectList,
            Ns.A + "blur", Ns.A + "fillOverlay", Ns.A + "glow", Ns.A + "innerShdw",
            Ns.A + "outerShdw", Ns.A + "prstShdw", Ns.A + "reflection", Ns.A + "softEdge");
    }