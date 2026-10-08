import org.aspose.pdf.Document;
import org.aspose.pdf.Page;
import org.aspose.pdf.Rectangle;
import org.aspose.pdf.annotations.FileAttachmentAnnotation;

public class PageAttachmentIcon {
    public static void main(String[] args) throws Exception {
        try (Document doc = new Document("input.pdf")) {
            Page page = doc.getPages().get_Item(1);   // 1-based

            FileAttachmentAnnotation ann =
                new FileAttachmentAnnotation(page, new Rectangle(50, 750, 70, 770));
            ann.setIcon("Paperclip");                 // Graph | PushPin | Paperclip | Tag

            page.getAnnotations().add(ann);
            doc.save("with-icon.pdf");
        }
    }
}
