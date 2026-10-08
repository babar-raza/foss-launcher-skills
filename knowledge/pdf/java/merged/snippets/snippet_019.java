import org.aspose.pdf.annotations.FileAttachmentAnnotation;
import java.io.FileOutputStream;

try (Document doc = new Document("input.pdf")) {
    int idx = 0;
    for (Page page : doc.getPages()) {
        for (Annotation a : page.getAnnotations()) {
            if (a instanceof FileAttachmentAnnotation) {
                FileAttachmentAnnotation att = (FileAttachmentAnnotation) a;
                // Use the FileAttachmentAnnotation API to access embedded data;
                // see JavaDoc for the current accessor name.
                idx++;
            }
        }
    }
}
