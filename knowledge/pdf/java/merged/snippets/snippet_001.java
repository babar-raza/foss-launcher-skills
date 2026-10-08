import org.aspose.pdf.Document;
import org.aspose.pdf.Page;
import org.aspose.pdf.Rectangle;
import org.aspose.pdf.Color;
import org.aspose.pdf.annotations.WidgetAnnotation;

try (Document doc = new Document()) {
    Page page = doc.getPages().add();

    WidgetAnnotation widget = new WidgetAnnotation(page, new Rectangle(0, 0, 100, 50));
    widget.getCharacteristics().setBorder(Color.fromRgb(1, 0, 0));

    Color border = widget.getCharacteristics().getBorder();
    System.out.println(border.getR() + ", " + border.getG() + ", " + border.getB());
}
