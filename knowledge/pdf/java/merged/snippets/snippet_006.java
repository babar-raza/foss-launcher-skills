import org.aspose.pdf.Document;
import org.aspose.pdf.forms.Form;
import org.aspose.pdf.forms.TextBoxField;

try (Document doc = new Document("form.pdf")) {
    Form form = doc.getForm();
    TextBoxField nameField = (TextBoxField) form.get("name");
    nameField.setValue("Jane Doe");

    // Iterate all fields
    for (org.aspose.pdf.forms.Field field : form.getFields()) {
        System.out.println(field.getPartialName() + " = " + field.getValue());
    }

    doc.save("form-filled.pdf");
}
