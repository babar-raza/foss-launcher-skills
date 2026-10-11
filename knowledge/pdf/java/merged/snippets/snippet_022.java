import org.aspose.pdf.Document;
import org.aspose.pdf.EmbeddedFileCollection;
import org.aspose.pdf.FileParams;
import org.aspose.pdf.FileSpecification;

public class ListAttachments {
    public static void main(String[] args) throws Exception {
        try (Document doc = new Document("with-attachment.pdf")) {
            EmbeddedFileCollection files = doc.getEmbeddedFiles();
            System.out.println("Attachments: " + files.getCount());

            // 1-based index
            for (int i = 1; i <= files.getCount(); i++) {
                FileSpecification fs = files.get(i);
                System.out.println("Name:        " + fs.getName());
                System.out.println("Unicode name:" + fs.getUnicodeFileName());
                System.out.println("Description: " + fs.getDescription());
                System.out.println("MIME type:   " + fs.getMIMEType());

                FileParams p = fs.getParams();
                if (p != null) {
                    System.out.println("Size:        " + p.getSize());
                    System.out.println("Created:     " + p.getCreationDate());
                    System.out.println("Modified:    " + p.getModDate());
                    System.out.println("CheckSum:    " + p.getCheckSum());
                }
                System.out.println("---");
            }

            // Or iterate directly:
            for (FileSpecification fs : files) {
                System.out.println(fs.getName());
            }
        }
    }
}
