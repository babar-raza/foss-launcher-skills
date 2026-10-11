import org.aspose.pdf.Document;
import org.aspose.pdf.FileSpecification;
import java.nio.file.Files;
import java.nio.file.Path;

public class ExtractAttachments {
    public static void main(String[] args) throws Exception {
        try (Document doc = new Document("with-attachment.pdf")) {
            var files = doc.getEmbeddedFiles();
            for (int i = 1; i <= files.getCount(); i++) {
                FileSpecification fs = files.get(i);
                byte[] data = fs.getData();
                if (data == null) {
                    continue;
                }
                String name = fs.getName() != null ? fs.getName() : ("file" + i);
                Path out = Path.of("extracted", name);
                Files.createDirectories(out.getParent());
                Files.write(out, data);
                System.out.println("Wrote " + out + " (" + data.length + " bytes)");
            }
        }
    }
}
