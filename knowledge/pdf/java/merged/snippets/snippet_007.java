try (Document doc = new Document()) {
    Page page = doc.getPages().add();
    Cell cell = new Cell();

    RadioButtonOptionField red = new RadioButtonOptionField(page, new Rectangle(0, 0, 10, 10));
    red.setOptionName("Red");
    RadioButtonOptionField green = new RadioButtonOptionField(page, new Rectangle(0, 0, 10, 10));
    green.setOptionName("Green");

    cell.add(red);
    cell.add(green);
    // Fields keep insertion order: cell.getParagraphs().get(0) is red, get(1) is green.
}
