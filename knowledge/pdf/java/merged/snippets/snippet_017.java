try (Document doc = new Document("input.pdf")) {
    for (Page page : doc.getPages()) {
        AnnotationCollection annots = page.getAnnotations();
        while (annots.getCount() > 0) {
            annots.delete(0);
        }
    }
    doc.save("no-annotations.pdf");
}
