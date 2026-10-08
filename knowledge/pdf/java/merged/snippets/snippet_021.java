import org.aspose.pdf.Document;
import org.aspose.pdf.FileSpecification;
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;

public class AttachFromStream {
    public static void main(String[] args) throws Exception {
        byte[] payload = "id,name\n1,Alice\n".getBytes(StandardCharsets.UTF_8);
        try (Document doc = new Document("input.pdf")) {
            FileSpecification fs = new FileSpecification(
                new ByteArrayInputStream(payload), "people.csv");
            fs.setDescription("Generated at runtime");
            fs.setMimeType("text/csv");

            doc.getEmbeddedFiles().add(fs);
            doc.save("with-attachment.pdf");
        }
    }
}
