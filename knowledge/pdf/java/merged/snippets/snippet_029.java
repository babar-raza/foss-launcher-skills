import org.aspose.pdf.Document;
import org.aspose.pdf.SaveFormat;

try (Document doc = new Document("input.pdf")) {
    doc.save("output.html", SaveFormat.Html);
}
