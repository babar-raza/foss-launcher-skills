import org.aspose.pdf.Document;
import org.aspose.pdf.XImage;

try (Document doc = new Document("input.pdf")) {
    int pageIndex = 1;
    int imageIndex = 1;
    for (XImage image : doc.getPages().get(pageIndex).getResources().getImages()) {
        try (java.io.FileOutputStream out = new java.io.FileOutputStream("image-" + imageIndex + ".png")) {
            image.save(out);
        }
        imageIndex++;
    }
}
