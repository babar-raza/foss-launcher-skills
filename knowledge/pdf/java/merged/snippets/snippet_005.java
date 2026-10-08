import org.aspose.pdf.Document;
import org.aspose.pdf.Page;
import org.aspose.pdf.text.TextFragment;

try (Document doc = new Document()) {
    Page page = doc.getPages().add();
    TextFragment fragment = new TextFragment("Hello, PDF world!");
    page.getParagraphs().add(fragment);
    doc.save("output.pdf");
}
