import org.aspose.pdf.Document;

public class DeleteAttachments {
    public static void main(String[] args) throws Exception {
        try (Document doc = new Document("with-attachment.pdf")) {
            var files = doc.getEmbeddedFiles();

            // Remove one by name:
            files.delete("report.csv");

            // Or remove the first by index (1-based):
            // files.delete(1);

            // Or remove everything:
            // files.delete();

            doc.save("cleaned.pdf");
        }
    }
}
