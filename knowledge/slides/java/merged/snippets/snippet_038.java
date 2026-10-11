@Test
    void removingTheLastParagraphMustLeaveTheTextBodyValid() throws Exception {
        Path out = tempDir.resolve("removed.pptx");
        try (var pres = new Presentation()) {
            IAutoShape shape = pres.getSlides().get(0).getShapes()
                    .addAutoShape(ShapeType.RECTANGLE, 50, 50, 400, 200);
            shape.addTextFrame("Only paragraph");
            var paragraphs = shape.getTextFrame().getParagraphs();
            while (paragraphs.size() > 0) {
                paragraphs.removeAt(0);
            }
            pres.save(out.toString(), SaveFormat.PPTX);
        }

        assertTextBodiesCarryAParagraph(out);
    }