import aspose.words_foss as aw

doc = aw.Document("report.docx")  # or .doc, .rtf, .txt, .md
doc.save("report.md", aw.SaveFormat.MARKDOWN)
