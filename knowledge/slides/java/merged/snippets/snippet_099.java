private static ITable findTable(ISlide slide) {
        for (int i = 0; i < slide.getShapes().size(); i++) {
            IShape shape = slide.getShapes().get(i);
            if (shape instanceof ITable table) {
                return table;
            }
        }
        return null;
    }