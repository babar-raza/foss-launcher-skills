import org.aspose.pdf.annotations.Border;
import org.aspose.pdf.annotations.BorderStyle;
import org.aspose.pdf.forms.RadioButtonOptionField;

RadioButtonOptionField option = new RadioButtonOptionField();
Border border = new Border(option);
border.setStyle(BorderStyle.Dashed);

Border roundTrip = option.getBorder();
System.out.println(roundTrip.getWidth());
