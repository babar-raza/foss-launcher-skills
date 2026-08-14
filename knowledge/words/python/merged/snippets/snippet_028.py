import aspose.words_foss as aw

doc = aw.Document("input.docx")  # or .doc, .rtf, .txt, .md
doc.save("output.md", aw.SaveFormat.MARKDOWN)
