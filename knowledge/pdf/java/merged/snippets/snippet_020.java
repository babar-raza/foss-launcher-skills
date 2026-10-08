import org.aspose.pdf.Document;
import org.aspose.pdf.FileSpecification;

public class AttachFile {
    public static void main(String[] args) throws Exception {
        try (Document doc = new Document("input.pdf")) {
            FileSpecification fs =
                new FileSpecification("data/report.csv", "Quarterly figures");
            fs.setMIMEType("text/csv");

            doc.getEmbeddedFiles().add(fs);
            doc.save("with-attachment.pdf");
        }
    }
}
