import org.aspose.pdf.Rectangle;
import org.aspose.pdf.annotations.HighlightAnnotation;

try (Document doc = new Document("input.pdf")) {
    Page page = doc.getPages().get(1);

    // Coordinates are in PDF user-space points, origin at lower-left
    Rectangle rect = new Rectangle(100, 700, 400, 720);
    HighlightAnnotation highlight = new HighlightAnnotation(page, rect);

    page.getAnnotations().add(highlight);
    doc.save("highlighted.pdf");
}
