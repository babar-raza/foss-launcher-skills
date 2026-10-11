import org.aspose.pdf.Document;
import org.aspose.pdf.Page;
import org.aspose.pdf.annotations.Annotation;
import org.aspose.pdf.annotations.AnnotationCollection;

try (Document doc = new Document("input.pdf")) {
    for (int i = 1; i <= doc.getPages().getCount(); i++) {
        Page page = doc.getPages().get(i);
        AnnotationCollection annots = page.getAnnotations();
        System.out.printf("Page %d has %d annotations%n", i, annots.getCount());
        for (Annotation a : annots) {
            System.out.printf("  %s at %s%n",
                a.getSubtype(),
                a.getRect());
        }
    }
}
