import org.aspose.pdf.annotations.MarkupAnnotation;

for (Annotation a : page.getAnnotations()) {
    if (a instanceof MarkupAnnotation) {
        MarkupAnnotation m = (MarkupAnnotation) a;
        // getAuthor(), getSubject(), getCreationDate() (where applicable)
    }
}
