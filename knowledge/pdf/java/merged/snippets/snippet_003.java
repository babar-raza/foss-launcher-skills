import org.aspose.pdf.Document;
import org.aspose.pdf.text.TextAbsorber;

try (Document doc = new Document("input.pdf")) {
    TextAbsorber absorber = new TextAbsorber();
    doc.getPages().accept(absorber);
    String text = absorber.getText();
    System.out.println(text);
}
