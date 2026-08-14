import aspose.words_foss as aw

doc = aw.Document("input.docx")
doc.save("output.pdf", aw.SaveFormat.PDF)
