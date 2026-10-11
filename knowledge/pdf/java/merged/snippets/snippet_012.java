import org.aspose.pdf.annotations.FreeTextAnnotation;
import org.aspose.pdf.annotations.DefaultAppearance;

try (Document doc = new Document("input.pdf")) {
    Page page = doc.getPages().get(1);
    Rectangle rect = new Rectangle(100, 600, 300, 650);

    FreeTextAnnotation note = new FreeTextAnnotation(
        page, rect, new DefaultAppearance(/* font, size, color */));
    note.setContents("Please review this section.");

    page.getAnnotations().add(note);
    doc.save("annotated.pdf");
}
