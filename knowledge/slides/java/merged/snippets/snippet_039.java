@Test
    void settingTheTextToNullMustLeaveTheTextBodyValid() throws Exception {
        Path out = tempDir.resolve("nulled.pptx");
        try (var pres = new Presentation()) {
            IAutoShape shape = pres.getSlides().get(0).getShapes()
                    .addAutoShape(ShapeType.RECTANGLE, 50, 50, 400, 200);
            shape.addTextFrame("Text that is then removed");
            shape.getTextFrame().setText(null);
            pres.save(out.toString(), SaveFormat.PPTX);
        }

        assertTextBodiesCarryAParagraph(out);
    }