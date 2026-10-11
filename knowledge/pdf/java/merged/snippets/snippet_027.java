import org.aspose.pdf.facades.PdfFileEditor;

public class MergeKeepsAttachments {
    public static void main(String[] args) throws Exception {
        PdfFileEditor editor = new PdfFileEditor();
        editor.concatenate(
            new String[] { "a.pdf", "b.pdf" },  // both may carry attachments
            "merged.pdf");
        // merged.pdf contains the embedded files from both a.pdf and b.pdf
    }
}
