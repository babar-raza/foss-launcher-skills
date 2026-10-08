try (Document doc = new Document()) {
    Page page = doc.getPages().add();
    WidgetAnnotation widget = new WidgetAnnotation(page, new Rectangle(0, 0, 100, 50));

    widget.getCharacteristics().setBackground(Color.fromRgb(0, 0.5, 0.5));
    Color background = widget.getCharacteristics().getBackground();
}
