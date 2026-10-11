import io
import aspose.words_foss as aw

markdown_with_image = (
    "# Report\n\n"
    "![logo](data:image/png;base64,iVBORw0KGgo...)\n\n"
    "See the [documentation](https://example.com/docs) for details.\n"
)

doc = aw.Document(io.BytesIO(markdown_with_image.encode("utf-8")), aw.MarkdownLoadOptions())
doc.save("report.docx", aw.SaveFormat.DOCX)  # image becomes a real embedded Shape
doc.save("report.pdf", aw.SaveFormat.PDF)    # link becomes a real clickable PDF annotation
