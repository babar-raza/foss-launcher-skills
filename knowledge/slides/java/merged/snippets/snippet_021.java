private Path writeDeckWithTable() throws Exception {
        Path out = tempDir.resolve("table.pptx");
        try (var pres = new Presentation()) {
            ITable table = pres.getSlides().get(0).getShapes()
                    .addTable(50, 50, new double[]{120, 120, 120}, new double[]{40, 40});
            table.getRows().get(0).get(0).getTextFrame().setText("Name");
            table.getRows().get(0).get(1).getTextFrame().setText("Value");
            pres.save(out.toString(), SaveFormat.PPTX);
        }
        return out;
    }