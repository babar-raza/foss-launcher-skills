@Test
    void aTextFrameEmptiedThroughTheCollectionMustStillCarryAParagraph() throws Exception {
        Path out = tempDir.resolve("cleared.pptx");
        try (var pres = new Presentation()) {
            IAutoShape shape = pres.getSlides().get(0).getShapes()
                    .addAutoShape(ShapeType.RECTANGLE, 50, 50, 400, 200);
            shape.addTextFrame("Text that is then removed");
            shape.getTextFrame().getParagraphs().clear();
            pres.save(out.toString(), SaveFormat.PPTX);
        }

        assertTextBodiesCarryAParagraph(out);
    }