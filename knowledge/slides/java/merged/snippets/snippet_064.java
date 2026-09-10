private Path writeFormattedRun(String fileName) throws Exception {
        Path out = tempDir.resolve(fileName);
        try (var pres = new Presentation()) {
            IAutoShape shape = pres.getSlides().get(0).getShapes()
                    .addAutoShape(ShapeType.RECTANGLE, 50, 50, 400, 150);
            shape.addTextFrame("Bold 24pt blue");
            IPortionFormat format = shape.getTextFrame().getParagraphs().get(0)
                    .getPortions().get(0).getPortionFormat();
            format.setFontHeight(24);
            format.setFontBold(NullableBool.TRUE);
            format.setFontItalic(NullableBool.TRUE);
            format.getFillFormat().setFillType(FillType.SOLID);
            format.getFillFormat().getSolidFillColor().setColor(Color.fromArgb(255, 0, 70, 127));
            pres.save(out.toString(), SaveFormat.PPTX);
        }
        return out;
    }