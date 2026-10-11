import org.aspose.pdf.Document;
import org.aspose.pdf.Page;
import org.aspose.pdf.Cell;
import org.aspose.pdf.Rectangle;
import org.aspose.pdf.forms.RadioButtonOptionField;
import org.aspose.pdf.text.TextFragment;

try (Document doc = new Document()) {
    Page page = doc.getPages().add();
    Cell cell = new Cell();

    cell.add(new TextFragment("Choose:"));

    RadioButtonOptionField red = new RadioButtonOptionField(page, new Rectangle(0, 0, 10, 10));
    red.setOptionName("Red");
    cell.add(red);

    System.out.println(cell.getParagraphs().size() + " paragraphs in the cell");
}
