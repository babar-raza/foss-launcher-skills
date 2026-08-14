import aspose.words_foss as aw

doc = aw.Document("input.docx")  # or .doc, .rtf
doc.save("output.docx", aw.SaveFormat.DOCX)
