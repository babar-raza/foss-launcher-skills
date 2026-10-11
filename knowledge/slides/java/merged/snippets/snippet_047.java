@Test
    void aPictureBulletMustResolveItsRelationship() throws Exception {
        Path out = tempDir.resolve("picture-bullet.pptx");
        try (var pres = new Presentation()) {
            IPPImage image = pres.getImages()
                    .addImage(Files.readAllBytes(Fixtures.testData("lotus.png")));
            IAutoShape shape = pres.getSlides().get(0).getShapes()
                    .addAutoShape(ShapeType.RECTANGLE, 50, 50, 400, 200);
            shape.addTextFrame("Bulleted line");
            IBulletFormat bullet = shape.getTextFrame().getParagraphs().get(0)
                    .getParagraphFormat().getBullet();
            bullet.setType(BulletType.PICTURE);
            bullet.getPicture().setImage(image);
            pres.save(out.toString(), SaveFormat.PPTX);
        }

        try (PptxPackage pkg = PptxPackage.open(out)) {
            List<Element> blips = PackageAssertions.selectNodes(
                    pkg, "ppt/slides/slide1.xml", "//a:pPr/a:buBlip/a:blip");
            assertThat(blips)
                    .as("a:buBlip/a:blip in slide 1 of %s%n%s",
                            out, pkg.text("ppt/slides/slide1.xml"))
                    .hasSize(1);

            String embedId = blips.get(0).getAttributeNS(PptxPackage.NS_REL, "embed");
            assertThat(embedId)
                    .as("r:embed of the bullet blip in %s%n%s",
                            out, pkg.text("ppt/slides/slide1.xml"))
                    .isNotEmpty();

            List<Element> relationships = PackageAssertions.selectNodes(
                    pkg, "ppt/slides/_rels/slide1.xml.rels",
                    "//rel:Relationship[@Id='" + embedId + "']");
            assertThat(relationships)
                    .as("relationship '%s' in ppt/slides/_rels/slide1.xml.rels of %s%n%s",
                            embedId, out, pkg.text("ppt/slides/_rels/slide1.xml.rels"))
                    .hasSize(1);

            String target = PptxPackage.resolveTarget(
                    "ppt/slides/slide1.xml", relationships.get(0).getAttribute("Target"));
            assertThat(pkg.hasPart(target))
                    .as("image part %s referenced by the bullet in %s", target, out)
                    .isTrue();

            PackageAssertions.assertEveryRelationshipReferenceResolves(pkg);
        }
    }