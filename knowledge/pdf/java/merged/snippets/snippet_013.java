import org.aspose.pdf.annotations.LinkAnnotation;

try (Document doc = new Document("input.pdf")) {
    Page page = doc.getPages().get(1);
    Rectangle rect = new Rectangle(100, 500, 400, 520);

    LinkAnnotation link = new LinkAnnotation(page, rect);
    // ... configure action: GoToURIAction or similar
    page.getAnnotations().add(link);
    doc.save("linked.pdf");
}
