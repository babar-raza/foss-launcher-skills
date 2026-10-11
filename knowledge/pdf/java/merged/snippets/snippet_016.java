AnnotationCollection annots = page.getAnnotations();

// Remove by index
annots.delete(0);

// Remove by reference
for (Annotation a : annots) {
    if ("...".equals(a.getContents())) {
        annots.delete(a);
        break;
    }
}
