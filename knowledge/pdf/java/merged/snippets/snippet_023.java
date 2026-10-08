FileSpecification fs = doc.getEmbeddedFiles().get("report.csv");
if (fs != null) {
    System.out.println(fs.getDescription());
}
