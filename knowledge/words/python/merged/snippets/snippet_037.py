import aspose.words_foss as aw

image_containing_files = [
    "simple_inline.docx",
    "image_with_caption.docx",
    "image_in_table.docx",
    "image_in_header.docx",
    "image_in_footer.docx",
]
for filename in image_containing_files:
    doc = aw.Document(filename)
    doc.save(f"{filename}.md", aw.SaveFormat.MARKDOWN)   # images embed as base64 by default
    doc.save(f"{filename}.pdf", aw.SaveFormat.PDF)        # rendered via ShapeRenderer
    doc.save(f"{filename}.txt", aw.SaveFormat.TEXT)
