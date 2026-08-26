import aspose.words_foss as aw

doc = aw.Document("report.docx")
doc.save("report.pdf", aw.SaveFormat.PDF)
